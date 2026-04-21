"""
app/api/v1/auth.py

Auth endpointlari:
  POST /auth/login          — email/parol bilan kirish
  POST /auth/telegram       — Telegram initData bilan kirish
  POST /auth/refresh        — tokenni yangilash
  POST /auth/logout         — chiqish
  GET  /auth/me             — joriy foydalanuvchi
  POST /auth/link-telegram  — web accountni Telegram bilan bog'lash
"""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.config import settings
from app.core.database import get_db_session
from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_current_token, get_tenant_session, require_any
from app.core.exceptions import (
    AuthInvalidInitData, AuthInsufficientRole,
    AuthTokenExpired, TenantNotFound,
)
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, verify_password, verify_telegram_init_data,
)
from app.models.public.tenant import Tenant
from app.models.tenant import User
from app.schemas import WebLoginRequest, TelegramAuthRequest, RefreshRequest, TokenResponse, ok
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(tags=["auth"])


async def _get_tenant(db, slug: str) -> Tenant:
    """Tenant ni slug bo'yicha topish."""
    stmt = select(Tenant).where(Tenant.slug == slug, Tenant.is_active == True)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    return tenant


async def _get_tenant_user(slug: str, email: str):
    """Tenant schemadan user ni email bo'yicha topish."""
    async with AsyncSessionLocal() as session:
        schema = f"tenant_{slug.replace('-', '_')}"
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        stmt = select(User).where(User.email == email)
        return (await session.execute(stmt)).scalar_one_or_none()


async def _get_tenant_user_by_tg(slug: str, telegram_id: int):
    """Tenant schemadan user ni telegram_id bo'yicha topish."""
    async with AsyncSessionLocal() as session:
        schema = f"tenant_{slug.replace('-', '_')}"
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        stmt = select(User).where(User.telegram_id == telegram_id)
        return (await session.execute(stmt)).scalar_one_or_none()


def _make_tokens(user: User, tenant_slug: str) -> dict:
    """JWT access + refresh token yaratish."""
    payload = {
        "sub":         str(user.id),
        "role":        user.role,
        "tenant_slug": tenant_slug,
        "branch_id":   str(user.branch_id) if getattr(user, "branch_id", None) else None,
    }
    access  = create_access_token(payload)
    refresh = create_refresh_token(payload)
    return {
        "access_token":  access,
        "refresh_token": refresh,
        "token_type":    "bearer",
        "user_id":       str(user.id),
        "role":          user.role,
        "tenant_slug":   tenant_slug,
        "branch_id":     str(user.branch_id) if getattr(user, "branch_id", None) else None,
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/login")
async def login(
    data: WebLoginRequest,
    db:   AsyncSession = Depends(get_db_session),
):
    """
    Email + parol bilan kirish.
    tenant_slug — qaysi ta'lim markazga kirilmoqda.
    """
    # Tenant mavjudligini tekshirish
    await _get_tenant(db, data.tenant_slug)

    # Foydalanuvchini topish
    user = await _get_tenant_user(data.tenant_slug, data.email)
    if not user:
        raise AuthTokenExpired()  # 401 — foydalanuvchi topilmadi

    # Parolni tekshirish
    if not user.password_hash or not verify_password(data.password, user.password_hash):
        raise AuthTokenExpired()  # 401 — parol noto'g'ri

    if not user.is_active:
        raise AuthInsufficientRole()  # 403 — deaktivlangan

    return ok(_make_tokens(user, data.tenant_slug))


@router.post("/telegram")
async def telegram_login(
    data: TelegramAuthRequest,
    db:   AsyncSession = Depends(get_db_session),
):
    """
    Telegram WebApp initData bilan kirish.
    HMAC-SHA256 server tomonida tekshiriladi.
    """
    # Tenant topish
    tenant = await _get_tenant(db, data.tenant_slug)

    # Bot token aniqlash (markaz o'z boti bo'lsa — shuni ishlatadi)
    bot_token = tenant.bot_token or settings.BOT_TOKEN
    if not bot_token:
        raise AuthInvalidInitData()

    # initData tekshirish
    tg_data = verify_telegram_init_data(data.init_data, bot_token)
    if not tg_data:
        raise AuthInvalidInitData()

    tg_user = tg_data.get("user", {})
    telegram_id = tg_user.get("id")
    if not telegram_id:
        raise AuthInvalidInitData()

    # Foydalanuvchini topish yoki yaratish
    user = await _get_tenant_user_by_tg(data.tenant_slug, telegram_id)

    if not user:
        # Yangi foydalanuvchi — invite link kerak, auto-register yo'q
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(
            status_code=403,
            detail={
                "code":       "USER_NOT_REGISTERED",
                "message":    "Siz ro'yxatdan o'tmagansiz. Admin bergan invite link orqali kiring.",
                "is_new_user": True,
                "telegram_id": telegram_id,
                "first_name":  tg_user.get("first_name", ""),
                "last_name":   tg_user.get("last_name", ""),
                "username":    tg_user.get("username", ""),
            }
        )

    return ok(_make_tokens(user, data.tenant_slug))


@router.post("/refresh")
async def refresh_token(data: RefreshRequest):
    """Refresh token orqali yangi access token olish."""
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthTokenExpired()

    new_access = create_access_token({
        "sub":         payload["sub"],
        "role":        payload["role"],
        "tenant_slug": payload["tenant_slug"],
    })
    return ok({"access_token": new_access, "token_type": "bearer"})


@router.post("/logout")
async def logout():
    """
    Logout — client token ni o'chiradi.
    Server tomonida token blacklist (Redis) keyinchalik qo'shiladi.
    """
    return ok({"message": "Chiqildi"})


@router.get("/me")
async def get_me(
    token: dict         = Depends(get_current_token),
    db:    AsyncSession = Depends(get_tenant_session),
):
    """Joriy foydalanuvchi ma'lumotlari."""
    user_id = uuid.UUID(token["sub"])
    stmt    = select(User).where(User.id == user_id)
    user    = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        raise AuthTokenExpired()

    return ok({
        "id":               str(user.id),
        "first_name":       user.first_name,
        "last_name":        user.last_name,
        "email":            user.email,
        "phone":            user.phone,
        "role":             user.role,
                "branch_id":        str(user.branch_id) if getattr(user, "branch_id", None) else None,
        "telegram_id":      user.telegram_id,
        "telegram_username":user.telegram_username,
        "avatar_url":       user.avatar_url,
        "language_code":    user.language_code,
        "is_active":        user.is_active,
        "is_verified":      user.is_verified,
        "created_at":       user.created_at.isoformat() if user.created_at else None,
    })


# ── Invite orqali ro'yxatdan o'tish ───────────────────────────────────

class RegisterRequest(BaseModel):
    tenant_slug:  str
    invite_code:  str
    init_data:    str            # Telegram WebApp initData
    phone:        Optional[str] = None
    first_name:   Optional[str] = None   # override Telegram data
    last_name:    Optional[str] = None


@router.post("/register")
async def register_via_invite(
    data: RegisterRequest,
    db:   AsyncSession = Depends(get_db_session),
):
    """
    Invite kodi orqali yangi foydalanuvchi ro'yxatdan o'tkazish.

    Qadamlar:
    1. Tenant topish
    2. initData tekshirish (Telegram)
    3. Invite kodi tekshirish → rol + group_id olish
    4. Foydalanuvchi allaqachon bormi?
    5. User + rol-specific profil (Teacher/Student/etc.) yaratish
    6. Invite kodni o'chirish (bir martalik)
    7. JWT tokens qaytarish
    """
    from app.core.invite_store import get_invite, delete_invite
    from app.models.tenant.student import Student
    from app.models.tenant.teacher import Teacher

    # 1. Tenant
    tenant = await _get_tenant(db, data.tenant_slug)

    # 2. Telegram auth
    bot_token = tenant.bot_token or settings.BOT_TOKEN
    if not bot_token:
        raise AuthInvalidInitData()

    tg_data = verify_telegram_init_data(data.init_data, bot_token)
    if not tg_data:
        raise AuthInvalidInitData()

    tg_user     = tg_data.get("user", {})
    telegram_id = tg_user.get("id")
    if not telegram_id:
        raise AuthInvalidInitData()

    # 3. Invite kodi
    code = data.invite_code.strip().upper()
    raw  = await get_invite(data.tenant_slug, code)
    if not raw:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Invite kod topilmadi yoki muddati o'tgan")

    # ── user_link:{user_id} — mavjud foydalanuvchiga Telegram bog'lash ──
    if raw.startswith("user_link:"):
        user_id_str = raw[len("user_link:"):]
        schema = f"tenant_{data.tenant_slug.replace('-', '_')}"
        async with AsyncSessionLocal() as session:
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            target_user = (await session.execute(
                select(User).where(User.id == uuid.UUID(user_id_str))
            )).scalar_one_or_none()
            if not target_user:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
            # Telegram ma'lumotlarini yangilash
            target_user.telegram_id       = telegram_id
            target_user.telegram_username = tg_user.get("username")
            if not target_user.first_name:
                target_user.first_name = data.first_name or tg_user.get("first_name", "")
            if not target_user.last_name:
                target_user.last_name = data.last_name or tg_user.get("last_name")
            target_user.is_active   = True
            target_user.is_verified = True
            await session.commit()
            await session.refresh(target_user)
        await delete_invite(data.tenant_slug, code)
        return ok({**(_make_tokens(target_user, data.tenant_slug)), "is_new_user": False, "role": target_user.role})

    # rol va group_id ajratish
    if ":" in raw:
        role, group_id_str = raw.split(":", 1)
        group_id = uuid.UUID(group_id_str)
    else:
        role     = raw
        group_id = None

    schema = f"tenant_{data.tenant_slug.replace('-', '_')}"

    # 4. Mavjud foydalanuvchini tekshirish
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        existing = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if existing:
            # Allaqachon ro'yxatdan o'tgan — token qaytaramiz
            await delete_invite(data.tenant_slug, code)
            return ok({**(_make_tokens(existing, data.tenant_slug)), "is_new_user": False})

        # 5. Yangi foydalanuvchi yaratish
        first_name = data.first_name or tg_user.get("first_name", "")
        last_name  = data.last_name  or tg_user.get("last_name")

        user = User(
            telegram_id=telegram_id,
            telegram_username=tg_user.get("username"),
            first_name=first_name,
            last_name=last_name,
            phone=data.phone or None,
            language_code=tg_user.get("language_code", "uz"),
            role=role,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()  # user.id olish uchun

        # Rol bo'yicha profil yaratish
        if role == "student":
            student = Student(user_id=user.id, is_approved=True, is_active=True)
            session.add(student)
            await session.flush()
            if group_id:
                from app.models.tenant.student import StudentGroup
                sg = StudentGroup(student_id=student.id, group_id=group_id)
                session.add(sg)

        elif role in ("teacher", "inspector"):
            teacher = Teacher(user_id=user.id, is_active=True)
            session.add(teacher)

        # parent — foydalanuvchi yaratiladi, farzand keyinchalik bog'lanadi

        await session.commit()
        await session.refresh(user)

    # 6. Invite o'chirish
    await delete_invite(data.tenant_slug, code)

    # 7. Tokens
    return ok({**(_make_tokens(user, data.tenant_slug)), "is_new_user": True, "role": role})
