"""
app/api/v1/superadmin.py

Super Admin endpointlari — barcha tenantlarni boshqarish.
Faqat super_admin roli kirishi mumkin.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_super_admin
from app.core.exceptions import TenantNotFound
from app.models.public.tenant import SubscriptionPlan, Tenant
from app.schemas import ok
from app.services.tenant_provisioning import (
    create_admin_user,
    create_default_branch,
    provision_tenant_schema,
)

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


# ─── Pydantic schemalar ───────────────────────────────────────────────

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])?$")


class TenantCreatePayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    plan_id: Optional[uuid.UUID] = None
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    bot_token: Optional[str] = None
    bot_username: Optional[str] = None
    custom_domain: Optional[str] = None
    trial_days: int = Field(14, ge=0, le=365)

    # Admin user — yangi tenant yaratilganda darhol admin tayinlash
    admin_email:      Optional[str] = Field(None, max_length=200)
    admin_password:   Optional[str] = Field(None, min_length=6, max_length=100)
    admin_first_name: Optional[str] = Field(None, max_length=100)
    admin_last_name:  Optional[str] = Field(None, max_length=100)
    admin_phone:      Optional[str] = Field(None, max_length=20)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not _SLUG_RE.match(v):
            raise ValueError("slug faqat kichik harf, raqam va tire (-) dan iborat bo'lishi kerak")
        return v


class TenantUpdatePayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    bot_token: Optional[str] = None
    bot_username: Optional[str] = None
    custom_domain: Optional[str] = None
    click_merchant_id: Optional[str] = None
    click_service_id: Optional[str] = None
    plan_id: Optional[uuid.UUID] = None


class PlanCreatePayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    slug: str = Field(..., min_length=2, max_length=30)
    price_monthly: int = Field(..., ge=0)
    max_students: Optional[int] = None
    max_teachers: Optional[int] = None
    max_branches: int = 1
    features: Dict[str, Any] = Field(default_factory=dict)


class PlanUpdatePayload(BaseModel):
    name: Optional[str] = None
    price_monthly: Optional[int] = Field(None, ge=0)
    max_students: Optional[int] = None
    max_teachers: Optional[int] = None
    max_branches: Optional[int] = None
    features: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ChangePlanPayload(BaseModel):
    plan_id: uuid.UUID


# ─── Helpers ──────────────────────────────────────────────────────────

def _tenant_dict(t: Tenant, plan: Optional[SubscriptionPlan] = None) -> dict:
    d = {
        "id":                  str(t.id),
        "slug":                t.slug,
        "name":                t.name,
        "schema_name":         t.schema_name,
        "phone":               t.phone,
        "address":             t.address,
        "subscription_status": t.subscription_status,
        "is_active":           t.is_active,
        "created_at":          t.created_at.isoformat() if t.created_at else None,
        "trial_ends_at":       t.trial_ends_at.isoformat() if t.trial_ends_at else None,
        "brand_color":         t.brand_color,
        "bot_username":        t.bot_username,
        "custom_domain":       t.custom_domain,
        "plan_id":             str(t.plan_id) if t.plan_id else None,
        "logo_url":            t.logo_url,
    }
    if plan:
        d["plan"] = {
            "id":            str(plan.id),
            "name":          plan.name,
            "slug":          plan.slug,
            "price_monthly": plan.price_monthly,
        }
    return d


def _plan_dict(p: SubscriptionPlan) -> dict:
    return {
        "id":            str(p.id),
        "name":          p.name,
        "slug":          p.slug,
        "price_monthly": p.price_monthly,
        "max_students":  p.max_students,
        "max_teachers":  p.max_teachers,
        "max_branches":  p.max_branches,
        "features":      p.features or {},
        "is_active":     p.is_active,
        "created_at":    p.created_at.isoformat() if p.created_at else None,
    }


async def _count_in_schema(session: AsyncSession, schema: str, table: str, where: str = "") -> int:
    try:
        sql = f'SELECT COUNT(*) FROM "{schema}"."{table}"'
        if where:
            sql += f" WHERE {where}"
        result = await session.execute(text(sql))
        return int(result.scalar() or 0)
    except Exception:
        return 0


# === Stats ============================================================

@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Platforma umumiy statistikasi (real ma'lumotlar)."""
    total_tenants = (await db.execute(select(func.count(Tenant.id)))).scalar_one() or 0
    active_tenants = (await db.execute(
        select(func.count(Tenant.id)).where(Tenant.subscription_status == "active")
    )).scalar_one() or 0
    trial_tenants = (await db.execute(
        select(func.count(Tenant.id)).where(Tenant.subscription_status == "trial")
    )).scalar_one() or 0
    suspended_tenants = (await db.execute(
        select(func.count(Tenant.id)).where(Tenant.subscription_status == "suspended")
    )).scalar_one() or 0

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_this_month = (await db.execute(
        select(func.count(Tenant.id)).where(Tenant.created_at >= month_start)
    )).scalar_one() or 0

    revenue_q = await db.execute(
        select(func.coalesce(func.sum(SubscriptionPlan.price_monthly), 0))
        .select_from(Tenant)
        .join(SubscriptionPlan, Tenant.plan_id == SubscriptionPlan.id)
        .where(Tenant.subscription_status == "active")
    )
    monthly_revenue = int(revenue_q.scalar() or 0)

    week_later = now + timedelta(days=7)
    trial_expiring = (await db.execute(
        select(func.count(Tenant.id)).where(
            Tenant.subscription_status == "trial",
            Tenant.trial_ends_at != None,  # noqa: E711
            Tenant.trial_ends_at <= week_later,
        )
    )).scalar_one() or 0

    return ok({
        "total_tenants":     total_tenants,
        "active_tenants":    active_tenants,
        "trial_tenants":     trial_tenants,
        "suspended_tenants": suspended_tenants,
        "new_this_month":    new_this_month,
        "monthly_revenue":   monthly_revenue,
        "trial_expiring":    trial_expiring,
    })


@router.get("/revenue/monthly")
async def revenue_monthly(
    months: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """So'nggi N oy uchun oylik daromad (faol tenantlar plan price summasi)."""
    now = datetime.now(timezone.utc)
    items = []
    for i in range(months - 1, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year += 1
        month_end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)

        revenue_q = await db.execute(
            select(func.coalesce(func.sum(SubscriptionPlan.price_monthly), 0))
            .select_from(Tenant)
            .join(SubscriptionPlan, Tenant.plan_id == SubscriptionPlan.id)
            .where(
                Tenant.created_at < month_end,
                Tenant.subscription_status.in_(["active", "trial"]),
            )
        )
        rev = int(revenue_q.scalar() or 0)
        items.append({
            "month": month_start.strftime("%Y-%m"),
            "label": month_start.strftime("%b"),
            "revenue": rev,
        })
    return ok(items)


# === Tenant CRUD =====================================================

@router.get("/tenants")
async def list_tenants(
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=100),
    search:   Optional[str] = Query(None),
    status:   Optional[str] = Query(None),
    plan_id:  Optional[str] = Query(None),
    db: AsyncSession        = Depends(get_db_session),
    _:  dict                = Depends(require_super_admin),
):
    """Barcha ta'lim markazlar ro'yxati + plan ma'lumoti bilan."""
    stmt = select(Tenant)

    if search:
        q = f"%{search}%"
        stmt = stmt.where(Tenant.name.ilike(q) | Tenant.slug.ilike(q))
    if status:
        stmt = stmt.where(Tenant.subscription_status == status)
    if plan_id:
        try:
            stmt = stmt.where(Tenant.plan_id == uuid.UUID(plan_id))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Noto'g'ri plan_id")

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    stmt = stmt.order_by(Tenant.created_at.desc()) \
               .offset((page - 1) * per_page).limit(per_page)
    tenants = (await db.execute(stmt)).scalars().all()

    plans_q = await db.execute(select(SubscriptionPlan))
    plans_by_id = {str(p.id): p for p in plans_q.scalars().all()}

    return ok(
        [_tenant_dict(t, plans_by_id.get(str(t.plan_id) if t.plan_id else "")) for t in tenants],
        {"page": page, "per_page": per_page, "total": total,
         "total_pages": (total + per_page - 1) // per_page},
    )


@router.post("/tenants", status_code=201)
async def create_tenant(
    payload: TenantCreatePayload,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """
    Yangi tenant yaratish:
      1. Slug band emasligini tekshirish
      2. Plan mavjudligini tekshirish (agar berilgan bo'lsa)
      3. Tenant yozuvi (public.tenants)
      4. PostgreSQL schema + barcha tenant jadvallari
      5. Admin foydalanuvchini schema'ga qo'shish (admin_email berilsa)
      6. Asosiy filial yaratish (admin uchun)
    """
    existing = (await db.execute(
        select(Tenant).where(Tenant.slug == payload.slug)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Bu slug band")

    if payload.plan_id:
        plan = (await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == payload.plan_id)
        )).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Tarif topilmadi")

    # Admin ma'lumotlarini tekshirish — agar email berilsa, parol va ism majburiy
    has_admin = bool(payload.admin_email)
    if has_admin:
        if not payload.admin_password or not payload.admin_first_name:
            raise HTTPException(
                status_code=400,
                detail="admin_email berilsa, admin_password va admin_first_name ham majburiy"
            )

    schema_name = f"tenant_{payload.slug.replace('-', '_')}"
    trial_ends = datetime.now(timezone.utc) + timedelta(days=payload.trial_days)

    tenant = Tenant(
        slug=payload.slug,
        name=payload.name,
        schema_name=schema_name,
        phone=payload.phone,
        address=payload.address,
        plan_id=payload.plan_id,
        subscription_status="trial" if not payload.plan_id else "active",
        trial_ends_at=trial_ends,
        brand_color=payload.brand_color or "#3B82F6",
        bot_token=payload.bot_token,
        bot_username=payload.bot_username,
        custom_domain=payload.custom_domain,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    admin_user_id: Optional[str] = None
    branch_id: Optional[str] = None

    try:
        # 1. Schema + jadvallar
        await provision_tenant_schema(db, schema_name)

        # 2. Asosiy filial (admin yaratiladigan bo'lsa)
        if has_admin:
            branch_id = await create_default_branch(
                db, schema_name,
                name=f"{payload.name} — asosiy filial",
                phone=payload.phone,
                address=payload.address,
            )
            # 3. Admin user
            admin_user_id = await create_admin_user(
                db, schema_name,
                email=payload.admin_email,
                password=payload.admin_password,
                first_name=payload.admin_first_name,
                last_name=payload.admin_last_name,
                phone=payload.admin_phone or payload.phone,
                branch_id=branch_id,
                role="admin",
            )
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Tenant yaratilmadi: {exc}"
        )

    await db.commit()
    await db.refresh(tenant)

    response_data = _tenant_dict(tenant)
    if admin_user_id:
        response_data["admin"] = {
            "id":         admin_user_id,
            "email":      payload.admin_email,
            "first_name": payload.admin_first_name,
            "last_name":  payload.admin_last_name,
            "branch_id":  branch_id,
            "login_url":  f"/login (tenant_slug: {payload.slug})",
        }
    return ok(response_data)


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Bitta tenant to'liq ma'lumoti + plan."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()

    plan = None
    if tenant.plan_id:
        plan = (await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == tenant.plan_id)
        )).scalar_one_or_none()

    return ok(_tenant_dict(tenant, plan))


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdatePayload,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenant ma'lumotlarini yangilash."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()

    data = payload.model_dump(exclude_unset=True)

    if "plan_id" in data and data["plan_id"]:
        plan = (await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == data["plan_id"])
        )).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Tarif topilmadi")

    for key, value in data.items():
        setattr(tenant, key, value)

    await db.commit()
    await db.refresh(tenant)
    return ok(_tenant_dict(tenant))


@router.delete("/tenants/{tenant_id}", status_code=200)
async def delete_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenantni soft-delete (is_active=False, status='cancelled')."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()

    tenant.is_active = False
    tenant.subscription_status = "cancelled"
    await db.commit()
    return ok({"message": "Tenant o'chirildi", "id": str(tenant_id)})


@router.get("/tenants/{tenant_id}/usage")
async def tenant_usage(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenant statistikasi: students/teachers/groups/branches/payments soni."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()

    schema = tenant.schema_name
    students_count = await _count_in_schema(db, schema, "students", "is_active = TRUE")
    teachers_count = await _count_in_schema(db, schema, "teachers", "is_active = TRUE")
    groups_count   = await _count_in_schema(db, schema, "groups",   "status = 'active'")
    branches_count = await _count_in_schema(db, schema, "branches", "is_active = TRUE")
    payments_count = await _count_in_schema(db, schema, "payments", "status = 'completed'")
    users_count    = await _count_in_schema(db, schema, "users",    "is_active = TRUE")

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_income = 0
    try:
        sql = f'SELECT COALESCE(SUM(amount), 0) FROM "{schema}"."payments" WHERE status = \'completed\' AND paid_at >= :start'
        result = await db.execute(text(sql), {"start": month_start})
        monthly_income = int(result.scalar() or 0)
    except Exception:
        pass

    return ok({
        "tenant_id":      str(tenant_id),
        "students_count": students_count,
        "teachers_count": teachers_count,
        "groups_count":   groups_count,
        "branches_count": branches_count,
        "payments_count": payments_count,
        "users_count":    users_count,
        "monthly_income": monthly_income,
    })


@router.post("/tenants/{tenant_id}/suspend", status_code=200)
async def suspend_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenantni to'xtatish."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    tenant.subscription_status = "suspended"
    tenant.is_active = False
    await db.commit()
    return ok({"message": "Tenant to'xtatildi", "id": str(tenant_id)})


@router.post("/tenants/{tenant_id}/activate", status_code=200)
async def activate_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenantni qayta faollashtirish."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    tenant.subscription_status = "active"
    tenant.is_active = True
    await db.commit()
    return ok({"message": "Tenant faollashtirildi", "id": str(tenant_id)})


@router.post("/tenants/{tenant_id}/change-plan", status_code=200)
async def change_tenant_plan(
    tenant_id: uuid.UUID,
    payload: ChangePlanPayload,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenant tarifini o'zgartirish va active qilish."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()

    plan = (await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == payload.plan_id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Tarif topilmadi")

    tenant.plan_id = payload.plan_id
    tenant.subscription_status = "active"
    tenant.is_active = True
    await db.commit()
    await db.refresh(tenant)
    return ok(_tenant_dict(tenant, plan))


# === Subscription plans CRUD ===========================================

@router.get("/plans")
async def list_plans(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Barcha tarif rejalari + har biriga tegishli tenantlar soni."""
    stmt = select(SubscriptionPlan)
    if not include_inactive:
        stmt = stmt.where(SubscriptionPlan.is_active == True)  # noqa: E712
    plans = (await db.execute(stmt.order_by(SubscriptionPlan.price_monthly))).scalars().all()

    counts_q = await db.execute(
        select(Tenant.plan_id, func.count(Tenant.id))
        .where(Tenant.is_active == True)  # noqa: E712
        .group_by(Tenant.plan_id)
    )
    counts = {str(pid): cnt for pid, cnt in counts_q.all() if pid}

    result = []
    for p in plans:
        d = _plan_dict(p)
        d["tenants_count"] = counts.get(str(p.id), 0)
        result.append(d)
    return ok(result)


@router.post("/plans", status_code=201)
async def create_plan(
    payload: PlanCreatePayload,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Yangi tarif yaratish."""
    existing = (await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.slug == payload.slug)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Bu slug band")

    plan = SubscriptionPlan(
        name=payload.name,
        slug=payload.slug,
        price_monthly=payload.price_monthly,
        max_students=payload.max_students,
        max_teachers=payload.max_teachers,
        max_branches=payload.max_branches,
        features=payload.features,
        is_active=True,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return ok(_plan_dict(plan))


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdatePayload,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tarif rejasini yangilash."""
    plan = (await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Tarif topilmadi")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(plan, key, value)

    await db.commit()
    await db.refresh(plan)
    return ok(_plan_dict(plan))


@router.delete("/plans/{plan_id}", status_code=200)
async def delete_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tarif rejasini soft-delete (is_active=False)."""
    plan = (await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Tarif topilmadi")

    tenants_count = (await db.execute(
        select(func.count(Tenant.id)).where(
            Tenant.plan_id == plan_id,
            Tenant.is_active == True,  # noqa: E712
        )
    )).scalar_one() or 0

    if tenants_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Bu tarifga {tenants_count} ta faol tenant ulangan."
        )

    plan.is_active = False
    await db.commit()
    return ok({"message": "Tarif o'chirildi", "id": str(plan_id)})


# === Tenant schema upgrade (mavjud tenantlarga yangi ustunlar qo'shish) ====

@router.post("/tenants/{tenant_id}/upgrade-schema", status_code=200)
async def upgrade_tenant_schema_endpoint(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """
    Tenant schema'ga barcha kerakli ustunlarni qo'shadi (008-013 migrations).
    Idempotent — qayta chaqirilsa xato bermaydi.
    Eski tenantlar uchun "alembic upgrade head" o'rniga ishlatish mumkin.
    """
    from app.services.tenant_provisioning import upgrade_tenant_schema

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()

    result = await upgrade_tenant_schema(db, tenant.schema_name)
    await db.commit()
    return ok({
        "tenant_id":     str(tenant_id),
        "schema_name":   tenant.schema_name,
        "applied_count": len(result["applied"]),
        "errors_count":  len(result["errors"]),
        "applied":       result["applied"],
        "errors":        result["errors"][:10],  # faqat birinchi 10 xato
    })


@router.post("/tenants/upgrade-all-schemas", status_code=200)
async def upgrade_all_tenant_schemas(
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """
    BARCHA faol tenantlar uchun schema upgrade.
    Mavjud DB'da migration tatbiq etilmagan bo'lsa, bu endpoint
    barcha tenantlarda yetishmayotgan ustunlarni qo'shadi.
    """
    from app.services.tenant_provisioning import upgrade_tenant_schema

    tenants = (await db.execute(
        select(Tenant).where(Tenant.is_active == True)  # noqa: E712
    )).scalars().all()

    results = []
    for t in tenants:
        try:
            r = await upgrade_tenant_schema(db, t.schema_name)
            results.append({
                "tenant_id":     str(t.id),
                "tenant_slug":   t.slug,
                "schema_name":   t.schema_name,
                "applied_count": len(r["applied"]),
                "errors_count":  len(r["errors"]),
            })
        except Exception as exc:
            results.append({
                "tenant_id":   str(t.id),
                "tenant_slug": t.slug,
                "error":       str(exc)[:200],
            })

    await db.commit()
    return ok({
        "total_tenants": len(tenants),
        "results":       results,
    })
