"""
app/api/v1/admin/users.py

Multi-role boshqaruv:
  GET    /users/lookup            — telefon yoki email bo'yicha mavjud user'ni topish
  GET    /users/{id}/roles        — user rollari ro'yxati
  POST   /users/{id}/roles        — user'ga yangi rol qo'shish (idempotent)
  DELETE /users/{id}/roles/{role} — user'dan rol olib tashlash (deaktivatsiya)
"""
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_token, get_tenant_session, require_admin,
)
from app.core.exceptions import EduSaaSException
from app.models.tenant import User
from app.schemas import ok
from app.services.user_roles import (
    list_active_roles, grant_role, revoke_role,
)

router = APIRouter(prefix="/users", tags=["users"])


# ─── Schemas ─────────────────────────────────────────────────────────

class UserLookupResult(BaseModel):
    id:                str
    first_name:        str
    last_name:         Optional[str] = None
    phone:             Optional[str] = None
    email:             Optional[str] = None
    avatar_url:        Optional[str] = None
    is_active:         bool
    branch_id:         Optional[str] = None
    telegram_id:       Optional[int] = None
    telegram_username: Optional[str] = None
    primary_role:      str           # users.role
    roles:             List[str]     # user_roles dan aktiv rollar


class GrantRoleRequest(BaseModel):
    role:      str
    branch_id: Optional[uuid.UUID] = None


# ─── Yordamchi ───────────────────────────────────────────────────────

async def _user_with_roles(db: AsyncSession, user: User) -> dict:
    roles = await list_active_roles(db, user.id)
    return {
        "id":                str(user.id),
        "first_name":        user.first_name,
        "last_name":         user.last_name,
        "phone":             user.phone,
        "email":             user.email,
        "avatar_url":        user.avatar_url,
        "is_active":         user.is_active,
        "branch_id":         str(user.branch_id) if user.branch_id else None,
        "telegram_id":       user.telegram_id,
        "telegram_username": user.telegram_username,
        "primary_role":      user.role,
        "roles":             roles,
    }


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("/lookup")
async def lookup_user(
    phone: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    db:    AsyncSession  = Depends(get_tenant_session),
    _:     dict          = Depends(require_admin),
):
    """
    Tenant ichidan user'ni telefon yoki email bo'yicha topish.
    Topilsa — rollari bilan birga qaytaradi (frontend "rolni qo'shamizmi?"
    banner'i uchun).
    """
    if not phone and not email:
        raise EduSaaSException(400, "BAD_REQUEST", "phone yoki email kerak")

    stmt = select(User)
    if phone:
        stmt = stmt.where(User.phone == phone.strip())
    elif email:
        stmt = stmt.where(User.email == email.strip().lower())

    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        return ok(None)
    return ok(await _user_with_roles(db, user))


@router.get("/{user_id}/roles")
async def get_user_roles(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise EduSaaSException(404, "USER_NOT_FOUND", "Foydalanuvchi topilmadi")
    return ok(await _user_with_roles(db, user))


@router.post("/{user_id}/roles", status_code=201)
async def attach_role(
    user_id: uuid.UUID,
    data:    GrantRoleRequest,
    db:      AsyncSession = Depends(get_tenant_session),
    tkn:     dict         = Depends(require_admin),
):
    """
    Mavjud user'ga yangi rol qo'shish.
    Misol: o'qituvchi → endi inspektor ham bo'lsin.
    """
    if data.role not in ("admin", "teacher", "inspector", "student", "parent"):
        raise EduSaaSException(400, "BAD_ROLE", "Yaroqsiz rol")

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise EduSaaSException(404, "USER_NOT_FOUND", "Foydalanuvchi topilmadi")

    granted_by = uuid.UUID(tkn["sub"])
    await grant_role(db, user.id, data.role, data.branch_id, granted_by)
    await db.commit()
    await db.refresh(user)
    return ok(await _user_with_roles(db, user))


class ChangeRoleRequest(BaseModel):
    from_role: str
    to_role:   str
    branch_id: Optional[uuid.UUID] = None


@router.post("/{user_id}/change-role")
async def change_role(
    user_id: uuid.UUID,
    data:    ChangeRoleRequest,
    db:      AsyncSession = Depends(get_tenant_session),
    tkn:     dict         = Depends(require_admin),
):
    """
    Foydalanuvchi rolini almashtirish (teacher ↔ inspector).
    `from_role` deaktivatsiya qilinadi, `to_role` qo'shiladi.
    `to_role == teacher` bo'lsa va Teacher profili yo'q bo'lsa — yaratiladi.
    """
    allowed = {"teacher", "inspector"}
    if data.from_role not in allowed or data.to_role not in allowed:
        raise EduSaaSException(400, "BAD_ROLE", "Faqat teacher↔inspector almashinuvi qo'llab-quvvatlanadi")
    if data.from_role == data.to_role:
        raise EduSaaSException(400, "SAME_ROLE", "Rollar bir xil")

    caller_role = tkn.get("role", "")
    if caller_role not in ("admin", "super_admin"):
        raise EduSaaSException(403, "FORBIDDEN", "Faqat admin/super_admin")

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise EduSaaSException(404, "USER_NOT_FOUND", "Foydalanuvchi topilmadi")

    granted_by = uuid.UUID(tkn["sub"])

    # 1. Eski rolni olib tashlash
    await revoke_role(db, user.id, data.from_role)

    # 2. Yangi rolni qo'shish
    await grant_role(db, user.id, data.to_role, data.branch_id, granted_by)

    # 3. Default users.role ni yangilash
    user.role = data.to_role
    if data.branch_id is not None:
        user.branch_id = data.branch_id

    # 4. Teacher profilini boshqarish
    from app.models.tenant import Teacher
    if data.to_role == "teacher":
        existing = (await db.execute(
            select(Teacher).where(Teacher.user_id == user.id)
        )).scalar_one_or_none()
        if existing:
            existing.is_active   = True
            existing.is_approved = True
            if data.branch_id is not None:
                existing.branch_id = data.branch_id
        else:
            db.add(Teacher(
                user_id=user.id,
                branch_id=data.branch_id,
                is_active=True,
                is_approved=True,
                created_by=granted_by,
                created_by_role=caller_role,
            ))
    elif data.from_role == "teacher":
        # Teacher profilini deaktivatsiya qilish (saqlab qolamiz, salohiyat tarixi yo'qolmasin)
        existing = (await db.execute(
            select(Teacher).where(Teacher.user_id == user.id)
        )).scalar_one_or_none()
        if existing:
            existing.is_active = False

    user.is_active = True
    await db.commit()
    await db.refresh(user)
    return ok(await _user_with_roles(db, user))


@router.delete("/{user_id}/roles/{role}", status_code=204)
async def detach_role(
    user_id: uuid.UUID,
    role:    str,
    db:      AsyncSession = Depends(get_tenant_session),
    _:       dict         = Depends(require_admin),
):
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise EduSaaSException(404, "USER_NOT_FOUND", "Foydalanuvchi topilmadi")
    await revoke_role(db, user.id, role)
    await db.commit()
