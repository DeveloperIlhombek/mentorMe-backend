"""
app/api/v1/admin/inspectors.py

Inspektorlar boshqaruvi (faqat admin).
"""
import random
import string
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin
from app.core.security import hash_password
from app.models.tenant import Branch, User
from app.schemas import ok

router = APIRouter(prefix="/inspectors", tags=["inspectors"])


# ─── Schemas ─────────────────────────────────────────────────────────

class InspectorCreate(BaseModel):
    first_name: str
    last_name:  Optional[str] = None
    phone:      Optional[str] = None
    email:      Optional[EmailStr] = None
    branch_id:  Optional[uuid.UUID] = None


class InspectorUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    phone:      Optional[str] = None
    email:      Optional[EmailStr] = None
    branch_id:  Optional[uuid.UUID] = None
    is_active:  Optional[bool] = None


# ─── Helper ──────────────────────────────────────────────────────────

def _user_dict(user: User) -> dict:
    return {
        "id":                 str(user.id),
        "first_name":         user.first_name,
        "last_name":          user.last_name,
        "phone":              user.phone,
        "email":              user.email,
        "avatar_url":         user.avatar_url,
        "is_active":          user.is_active,
        "is_verified":        user.is_verified,
        "branch_id":          str(user.branch_id) if user.branch_id else None,
        "telegram_id":        user.telegram_id,
        "telegram_username":  user.telegram_username,
        "created_at":         user.created_at.isoformat(),
    }


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("")
async def list_inspectors(
    page:      int           = Query(1, ge=1),
    per_page:  int           = Query(20, ge=1, le=500),
    search:    Optional[str] = Query(None),
    is_active: Optional[bool]= Query(None),
    db: AsyncSession         = Depends(get_tenant_session),
    _:  dict                 = Depends(require_admin),
):
    stmt = select(User).where(User.role == "inspector")
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if search:
        q = f"%{search}%"
        stmt = stmt.where(or_(
            User.first_name.ilike(q),
            User.last_name.ilike(q),
            User.phone.ilike(q),
        ))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt  = stmt.order_by(User.first_name).offset((page - 1) * per_page).limit(per_page)
    users = (await db.execute(stmt)).scalars().all()

    pages = (total + per_page - 1) // per_page
    return ok([_user_dict(u) for u in users], {
        "page": page, "per_page": per_page,
        "total": total, "total_pages": pages,
    })


@router.post("", status_code=201)
async def create_inspector(
    data: InspectorCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        email=data.email,
        role="inspector",
        branch_id=data.branch_id,
        password_hash=hash_password("Inspector123!"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ok(_user_dict(user))


@router.get("/{inspector_id}")
async def get_inspector(
    inspector_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    user = (await db.execute(
        select(User).where(User.id == inspector_id, User.role == "inspector")
    )).scalar_one_or_none()
    if not user:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "INSPECTOR_NOT_FOUND", "Inspektor topilmadi")
    return ok(_user_dict(user))


@router.patch("/{inspector_id}")
async def update_inspector(
    inspector_id: uuid.UUID,
    data: InspectorUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    user = (await db.execute(
        select(User).where(User.id == inspector_id, User.role == "inspector")
    )).scalar_one_or_none()
    if not user:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "INSPECTOR_NOT_FOUND", "Inspektor topilmadi")

    if data.first_name is not None: user.first_name = data.first_name
    if data.last_name  is not None: user.last_name  = data.last_name
    if data.phone      is not None: user.phone      = data.phone
    if data.email      is not None: user.email      = data.email
    if data.branch_id  is not None: user.branch_id  = data.branch_id
    if data.is_active  is not None: user.is_active  = data.is_active

    await db.commit()
    await db.refresh(user)
    return ok(_user_dict(user))


@router.delete("/{inspector_id}", status_code=204)
async def delete_inspector(
    inspector_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    user = (await db.execute(
        select(User).where(User.id == inspector_id, User.role == "inspector")
    )).scalar_one_or_none()
    if user:
        user.is_active = False
        await db.commit()


@router.post("/{inspector_id}/generate-invite")
async def generate_inspector_invite(
    inspector_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    """
    Inspektor uchun Telegram aktivatsiya havolasi yaratish.
    Inspektor bu link orqali Telegram profilini bog'laydi.
    Payload: user_link:{user_id}
    """
    from app.core.config import settings
    from app.core.invite_store import store_invite

    user = (await db.execute(
        select(User).where(User.id == inspector_id, User.role == "inspector")
    )).scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Inspektor topilmadi")

    tenant_slug = tkn.get("tenant_slug", "default")
    code = "INS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    await store_invite(tenant_slug, code, f"user_link:{str(user.id)}")

    bot_username = getattr(settings, "BOT_USERNAME", "edusaasbot")
    deep_link    = f"https://t.me/{bot_username}?startapp=inv_{tenant_slug}_{code}"
    webapp_link  = f"{settings.FRONTEND_URL.rstrip('/')}/uz/onboarding?code={code}&tenant={tenant_slug}"

    return ok({
        "invite_code":     code,
        "deep_link":       deep_link,
        "webapp_link":     webapp_link,
        "inspector_id":    str(inspector_id),
        "inspector_name":  f"{user.first_name} {user.last_name or ''}".strip(),
        "expires_hours":   48,
    })
