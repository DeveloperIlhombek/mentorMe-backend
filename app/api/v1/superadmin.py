"""
app/api/v1/superadmin.py

Super Admin endpointlari — barcha tenantlarni boshqarish.
Faqat super_admin roli kirishi mumkin.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_super_admin
from app.core.exceptions import TenantNotFound
from app.models.public.tenant import Tenant, SubscriptionPlan
from app.schemas import ok

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


@router.get("/tenants")
async def list_tenants(
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=100),
    search:   Optional[str] = Query(None),
    status:   Optional[str] = Query(None),
    db: AsyncSession        = Depends(get_db_session),
    _:  dict                = Depends(require_super_admin),
):
    """Barcha ta'lim markazlar ro'yxati."""
    stmt = select(Tenant)

    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            Tenant.name.ilike(q) | Tenant.slug.ilike(q)
        )
    if status:
        stmt = stmt.where(Tenant.subscription_status == status)

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    stmt = stmt.order_by(Tenant.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    tenants = (await db.execute(stmt)).scalars().all()

    return ok(
        [_tenant_dict(t) for t in tenants],
        {"page": page, "per_page": per_page, "total": total,
         "total_pages": (total + per_page - 1) // per_page},
    )


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Bitta tenant to'liq ma'lumoti."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    return ok(_tenant_dict(tenant))


@router.post("/tenants/{tenant_id}/suspend", status_code=200)
async def suspend_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenantni to'xtatish."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    tenant.subscription_status = "suspended"
    tenant.is_active = False
    await db.commit()
    return ok({"message": "Tenant to'xtatildi"})


@router.post("/tenants/{tenant_id}/activate", status_code=200)
async def activate_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Tenantni qayta faollashtirish."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    tenant.subscription_status = "active"
    tenant.is_active = True
    await db.commit()
    return ok({"message": "Tenant faollashtirildi"})


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Platforma umumiy statistikasi."""
    total_tenants  = (await db.execute(select(func.count(Tenant.id)))).scalar_one()
    active_tenants = (await db.execute(
        select(func.count(Tenant.id)).where(Tenant.subscription_status == "active")
    )).scalar_one()
    trial_tenants  = (await db.execute(
        select(func.count(Tenant.id)).where(Tenant.subscription_status == "trial")
    )).scalar_one()

    return ok({
        "total_tenants":  total_tenants,
        "active_tenants": active_tenants,
        "trial_tenants":  trial_tenants,
        "suspended_tenants": total_tenants - active_tenants - trial_tenants,
    })


@router.get("/plans")
async def list_plans(
    db: AsyncSession = Depends(get_db_session),
    _:  dict         = Depends(require_super_admin),
):
    """Barcha tarif rejalari."""
    stmt  = select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)
    plans = (await db.execute(stmt)).scalars().all()
    return ok([
        {
            "id":            str(p.id),
            "name":          p.name,
            "slug":          p.slug,
            "price_monthly": p.price_monthly,
            "max_students":  p.max_students,
            "max_teachers":  p.max_teachers,
            "max_branches":  p.max_branches,
            "features":      p.features,
        }
        for p in plans
    ])


def _tenant_dict(t: Tenant) -> dict:
    return {
        "id":                  str(t.id),
        "slug":                t.slug,
        "name":                t.name,
        "schema_name":         t.schema_name,
        "phone":               t.phone,
        "subscription_status": t.subscription_status,
        "is_active":           t.is_active,
        "created_at":          t.created_at.isoformat() if t.created_at else None,
        "trial_ends_at":       t.trial_ends_at.isoformat() if t.trial_ends_at else None,
        "brand_color":         t.brand_color,
    }
