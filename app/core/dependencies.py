from typing import Annotated, Optional
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.core.exceptions import (
    AuthTokenExpired,
    AuthInsufficientRole,
    TenantNotFound,
)

security = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_token(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> dict:
    if not credentials:
        raise AuthTokenExpired()
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise AuthTokenExpired()
    return payload


async def get_tenant_slug(
    x_tenant_slug: Annotated[Optional[str], Header()] = None,
    token: Annotated[Optional[dict], Depends(get_current_token)] = None,
) -> str:
    slug = x_tenant_slug or (token.get("tenant_slug") if token else None)
    if not slug:
        raise TenantNotFound()
    return slug


async def get_tenant_session(
    tenant_slug: Annotated[str, Depends(get_tenant_slug)],
) -> AsyncSession:
    async with AsyncSessionLocal() as session:
        schema = f"tenant_{tenant_slug.replace('-', '_')}"
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def require_role(*roles: str):
    """Role-based access control dependency factory."""
    async def _check(token: Annotated[dict, Depends(get_current_token)]) -> dict:
        if token.get("role") not in roles:
            raise AuthInsufficientRole()
        return token
    return _check


# ─── Shorthand role checks ────────────────────────────────────────────
require_super_admin = require_role("super_admin")
require_admin       = require_role("super_admin", "admin")
require_inspector   = require_role("super_admin", "admin", "inspector")
require_teacher     = require_role("super_admin", "admin", "inspector", "teacher")
require_student     = require_role("super_admin", "admin", "inspector", "teacher", "student")
require_parent      = require_role("super_admin", "admin", "parent")
require_any         = require_role("super_admin", "admin", "inspector", "teacher", "student", "parent")


# ─── Branch filter — inspektor uchun ─────────────────────────────────

async def get_branch_filter(
    token: Annotated[dict, Depends(get_current_token)],
    db:    AsyncSession = Depends(get_tenant_session),
) -> Optional[str]:
    """
    Inspektor bo'lsa → uning branch_id sini qaytaradi (UUID string).
    Admin bo'lsa → None (barcha filiallar ko'rinadi).
    Endpoint da: branch_id = Depends(get_branch_filter)
    """
    role = token.get("role")
    if role in ("super_admin", "admin"):
        return None   # cheklov yo'q

    if role == "inspector":
        user_id = token.get("sub")
        if not user_id:
            raise AuthInsufficientRole()
        from app.models.tenant.user import User
        import uuid as _uuid
        user = (await db.execute(
            select(User).where(User.id == _uuid.UUID(user_id))
        )).scalar_one_or_none()
        if not user or not user.branch_id:
            raise AuthInsufficientRole()
        return str(user.branch_id)

    raise AuthInsufficientRole()


async def get_optional_branch_filter(
    token: Annotated[dict, Depends(get_current_token)],
    db:    AsyncSession = Depends(get_tenant_session),
) -> Optional[str]:
    """
    Admin + Inspector uchun. Inspector uchun branch_id qaytaradi.
    Teacher va boshqalar uchun None (o'z endpoint lari bor).
    """
    role = token.get("role")
    if role in ("super_admin", "admin"):
        return None
    if role == "inspector":
        user_id = token.get("sub")
        from app.models.tenant.user import User
        import uuid as _uuid
        user = (await db.execute(
            select(User).where(User.id == _uuid.UUID(user_id))
        )).scalar_one_or_none()
        return str(user.branch_id) if user and user.branch_id else None
    return None
