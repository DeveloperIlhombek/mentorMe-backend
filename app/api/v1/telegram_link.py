"""
app/api/v1/telegram_link.py

Admin foydalanuvchiga deep-link token generate qiladi:
  POST /api/v1/admin/users/{user_id}/telegram-link
    → {token, deep_link, expires_at}

Foydalanuvchi t.me/<bot>?start=<token> orqali kiradi va telegram_id avtomatik
biriktiriladi (bot/handlers/start.py ichida).
"""
import secrets
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_tenant_session, get_tenant_slug, require_admin
from app.models.tenant.user import User
from app.schemas import ok

router = APIRouter(prefix="/admin/users", tags=["admin", "telegram-link"])


@router.post("/{user_id}/telegram-link")
async def create_telegram_link(
    user_id: uuid.UUID,
    db:          AsyncSession = Depends(get_tenant_session),
    tenant_slug: str          = Depends(get_tenant_slug),
    _tkn:        dict         = Depends(require_admin),
):
    """Foydalanuvchi uchun deep-link token yaratish (TTL: 7 kun)."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    token   = secrets.token_urlsafe(32)
    expires = _utcnow() + timedelta(days=settings.NOTIF_LINK_TOKEN_TTL_DAYS)

    user.telegram_link_token      = token
    user.telegram_link_expires_at = expires
    await db.flush()

    # Public schema'ga ham yozish (bot bularni tezda topishi uchun)
    async with AsyncSessionLocal() as pub:
        await pub.execute(text("""
            INSERT INTO public.telegram_link_tokens (token, tenant_slug, user_id, expires_at)
            VALUES (:token, :slug, :uid, :exp)
            ON CONFLICT (token) DO UPDATE SET expires_at = EXCLUDED.expires_at
        """), {"token": token, "slug": tenant_slug, "uid": str(user_id), "exp": expires})
        await pub.commit()

    bot_username = (settings.BOT_USERNAME or "").lstrip("@")
    deep_link    = f"https://t.me/{bot_username}?start={token}" if bot_username else None

    return ok({
        "token":      token,
        "deep_link":  deep_link,
        "expires_at": expires.isoformat(),
        "user": {
            "id":         str(user.id),
            "first_name": user.first_name,
            "role":       user.role,
        },
    })


@router.delete("/{user_id}/telegram-link")
async def revoke_telegram_link(
    user_id: uuid.UUID,
    db:          AsyncSession = Depends(get_tenant_session),
    tenant_slug: str          = Depends(get_tenant_slug),
    _tkn:        dict         = Depends(require_admin),
):
    """Token va biriktirishni bekor qilish."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    old_token = user.telegram_link_token
    user.telegram_link_token      = None
    user.telegram_link_expires_at = None
    user.telegram_id              = None
    user.telegram_linked_at       = None
    await db.flush()

    if old_token:
        async with AsyncSessionLocal() as pub:
            await pub.execute(text(
                "DELETE FROM public.telegram_link_tokens WHERE token = :t"
            ), {"t": old_token})
            await pub.commit()

    return ok({"revoked": True})


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
