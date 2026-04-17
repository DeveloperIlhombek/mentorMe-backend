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
        # Yangi foydalanuvchi — auto-register (student sifatida)
        async with AsyncSessionLocal() as session:
            schema = f"tenant_{data.tenant_slug.replace('-', '_')}"
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            user = User(
                telegram_id=telegram_id,
                telegram_username=tg_user.get("username"),
                first_name=tg_user.get("first_name", ""),
                last_name=tg_user.get("last_name"),
                language_code=tg_user.get("language_code", "uz"),
                role="student",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

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
