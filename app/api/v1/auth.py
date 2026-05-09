"""
app/api/v1/auth.py

Auth endpointlari:
  POST /auth/login          — email/parol bilan kirish
  POST /auth/telegram       — Telegram initData bilan kirish
  POST /auth/refresh        — tokenni yangilash
  POST /auth/logout         — chiqish (token blacklist)
  GET  /auth/me             — joriy foydalanuvchi
  POST /auth/register       — invite kodi orqali ro'yxatdan o'tish
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db_session
from app.core.dependencies import get_current_token, get_tenant_session
from app.core.exceptions import (
    AuthAccountInactive, AuthInvalidCredentials, AuthInvalidInitData,
    AuthInsufficientRole, AuthTokenExpired, InvalidTenantSlug, TenantNotFound,
)
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, is_valid_tenant_slug, tenant_schema_name,
    verify_password, verify_telegram_init_data,
)
from app.core.token_blacklist import blacklist_token
from app.models.public.tenant import Tenant
from app.models.tenant import User
from app.schemas import WebLoginRequest, TelegramAuthRequest, RefreshRequest, ok

router = APIRouter(tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────

async def _get_tenant(db, slug: str) -> Tenant:
    """Tenant ni slug bo'yicha topish."""
    stmt = select(Tenant).where(Tenant.slug == slug, Tenant.is_active == True)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if not tenant:
        raise TenantNotFound()
    return tenant


async def _get_tenant_user(slug: str, email: str):
    """Tenant schemadan user ni email bo'yicha topish."""
    schema = tenant_schema_name(slug)
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        stmt = select(User).where(User.email == email)
        return (await session.execute(stmt)).scalar_one_or_none()


async def _get_tenant_user_by_tg(slug: str, telegram_id: int):
    """Tenant schemadan user ni telegram_id bo'yicha topish."""
    schema = tenant_schema_name(slug)
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        stmt = select(User).where(User.telegram_id == telegram_id)
        return (await session.execute(stmt)).scalar_one_or_none()


async def _get_tenant_user_by_id(slug: str, user_id: uuid.UUID):
    """Tenant schemadan user ni id bo'yicha topish (refresh uchun)."""
    schema = tenant_schema_name(slug)
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        stmt = select(User).where(User.id == user_id)
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


def _ensure_active(user: User) -> None:
    """Faol foydalanuvchini tekshirish."""
    if not user.is_active:
        raise AuthAccountInactive()


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/login")
async def login(
    data: WebLoginRequest,
    db:   AsyncSession = Depends(get_db_session),
):
    """
    Email + parol bilan kirish.

    tenant_slug — ixtiyoriy:
      - berilmasa, super_admin uchun 'platform' tenant'i sinab ko'riladi
      - bo'lmasa, barcha tenantlar bo'yicha email qidiriladi (avtomatik aniqlash)
      - oddiy admin/teacher uchun aniq slug berilishi tavsiya etiladi
    """
    candidate_slugs: list[str] = []

    if data.tenant_slug:
        # Aniq tenant berilgan
        if not is_valid_tenant_slug(data.tenant_slug):
            raise InvalidTenantSlug()
        candidate_slugs = [data.tenant_slug]
    else:
        # 1. Avval 'platform' (super_admin uchun)
        platform_t = (await db.execute(
            select(Tenant).where(Tenant.slug == "platform", Tenant.is_active == True)  # noqa: E712
        )).scalar_one_or_none()
        if platform_t:
            candidate_slugs.append("platform")

        # 2. Boshqa barcha faol tenantlar (oddiy admin email avtomatik aniqlash uchun)
        all_tenants = (await db.execute(
            select(Tenant.slug).where(Tenant.is_active == True)  # noqa: E712
        )).scalars().all()
        for s in all_tenants:
            if s not in candidate_slugs:
                candidate_slugs.append(s)

    # Har bir candidate slug uchun userni qidirish
    user = None
    matched_slug: Optional[str] = None
    for slug in candidate_slugs:
        u = await _get_tenant_user(slug, data.email)
        if u:
            user = u
            matched_slug = slug
            break

    if not user or not matched_slug:
        # Foydalanuvchi topilmadi — user enumeration'dan himoya uchun
        # parol noto'g'ri bilan bir xil javob beramiz.
        raise AuthInvalidCredentials()

    # Parolni tekshirish
    if not user.password_hash or not verify_password(data.password, user.password_hash):
        raise AuthInvalidCredentials()

    _ensure_active(user)

    # Tenant mavjudligini tekshirish (qo'shimcha xavfsizlik)
    await _get_tenant(db, matched_slug)

    return ok(_make_tokens(user, matched_slug))


@router.post("/telegram")
async def telegram_login(
    data: TelegramAuthRequest,
    db:   AsyncSession = Depends(get_db_session),
):
    """
    Telegram WebApp initData bilan kirish.
    HMAC-SHA256 + auth_date timestamp tekshiruvi.
    """
    if not is_valid_tenant_slug(data.tenant_slug):
        raise InvalidTenantSlug()
    tenant = await _get_tenant(db, data.tenant_slug)

    bot_token = tenant.bot_token or settings.BOT_TOKEN
    if not bot_token:
        raise AuthInvalidInitData()

    tg_data = verify_telegram_init_data(data.init_data, bot_token)
    if not tg_data:
        raise AuthInvalidInitData()

    tg_user = tg_data.get("user", {})
    telegram_id = tg_user.get("id")
    if not telegram_id:
        raise AuthInvalidInitData()

    user = await _get_tenant_user_by_tg(data.tenant_slug, telegram_id)

    if not user:
        # Yangi foydalanuvchi — invite link kerak
        raise HTTPException(
            status_code=403,
            detail={
                "code":        "USER_NOT_REGISTERED",
                "message":     "Siz ro'yxatdan o'tmagansiz. Admin bergan invite link orqali kiring.",
                "is_new_user": True,
                "telegram_id": telegram_id,
                "first_name":  tg_user.get("first_name", ""),
                "last_name":   tg_user.get("last_name", ""),
                "username":    tg_user.get("username", ""),
            }
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "code":    "USER_DEACTIVATED",
                "message": "Hisobingiz deaktivlangan. Admin bilan bog'laning.",
            }
        )

    return ok(_make_tokens(user, data.tenant_slug))


@router.post("/refresh")
async def refresh_token(
    data: RefreshRequest,
    x_tenant_slug: Optional[str] = Header(default=None, alias="X-Tenant-Slug"),
):
    """
    Refresh token orqali yangi access + refresh token olish.
    Refresh token rotation: eski refresh blacklist'ga, yangi token qaytariladi.
    """
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthTokenExpired()

    # Tenant izolatsiyasi: header'dagi tenant payload'dagi bilan bir xil bo'lishi shart.
    tenant_slug = payload.get("tenant_slug")
    if not tenant_slug or not is_valid_tenant_slug(tenant_slug):
        raise AuthTokenExpired()
    # Header berilgan bo'lsa — albatta moslashishi kerak.
    if x_tenant_slug and x_tenant_slug != tenant_slug:
        raise AuthInsufficientRole()

    # Eski refresh tokenni avval blacklist'da tekshiramiz — DB ishini bekor qilish uchun.
    from app.core.token_blacklist import is_blacklisted
    jti = payload.get("jti")
    if await is_blacklisted(jti):
        raise AuthTokenExpired()

    # Foydalanuvchi hali ham mavjud va faolmi?
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthTokenExpired()
    try:
        user_id = uuid.UUID(user_id_str)
    except (TypeError, ValueError):
        raise AuthTokenExpired()

    user = await _get_tenant_user_by_id(tenant_slug, user_id)
    if not user or not user.is_active:
        raise AuthTokenExpired()

    # Rotation: eski refresh tokenni blacklist'ga
    await blacklist_token(jti, int(payload.get("exp", 0)))

    tokens = _make_tokens(user, tenant_slug)
    return ok(tokens)


@router.post("/logout")
async def logout(token: dict = Depends(get_current_token)):
    """
    Logout — access tokenni blacklist'ga qo'shadi.
    Frontend o'z tomonida ham token va cookie'ni o'chirishi kerak.
    """
    jti = token.get("jti")
    exp = int(token.get("exp", 0))
    if jti:
        await blacklist_token(jti, exp)
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
    if not user.is_active:
        raise AuthInsufficientRole()

    return ok({
        "id":                str(user.id),
        "first_name":        user.first_name,
        "last_name":         user.last_name,
        "email":             user.email,
        "phone":             user.phone,
        "role":              user.role,
        "branch_id":         str(user.branch_id) if getattr(user, "branch_id", None) else None,
        "telegram_id":       user.telegram_id,
        "telegram_username": user.telegram_username,
        "avatar_url":        user.avatar_url,
        "language_code":     user.language_code,
        "is_active":         user.is_active,
        "is_verified":       user.is_verified,
        "created_at":        user.created_at.isoformat() if user.created_at else None,
    })


# ── Invite orqali ro'yxatdan o'tish ───────────────────────────────────

class RegisterRequest(BaseModel):
    tenant_slug:  str
    invite_code:  str
    init_data:    str            # Telegram WebApp initData
    phone:        Optional[str] = None
    first_name:   Optional[str] = None
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
    2. initData tekshirish (Telegram + timestamp)
    3. Invite kodi tekshirish → rol + group_id olish
    4. Foydalanuvchi allaqachon bormi?
    5. User + rol-specific profil (Teacher/Student/etc.) yaratish
    6. Invite kodni o'chirish (bir martalik)
    7. JWT tokens qaytarish
    """
    from app.core.invite_store import get_invite, delete_invite
    from app.models.tenant.student import Student
    from app.models.tenant.teacher import Teacher

    if not is_valid_tenant_slug(data.tenant_slug):
        raise InvalidTenantSlug()
    tenant = await _get_tenant(db, data.tenant_slug)

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

    code = data.invite_code.strip().upper()
    raw  = await get_invite(data.tenant_slug, code)
    if not raw:
        raise HTTPException(status_code=404, detail="Invite kod topilmadi yoki muddati o'tgan")

    schema = tenant_schema_name(data.tenant_slug)

    # ── user_link:{user_id} — mavjud foydalanuvchiga Telegram bog'lash ──
    if raw.startswith("user_link:"):
        user_id_str = raw[len("user_link:"):]
        async with AsyncSessionLocal() as session:
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            target_user = (await session.execute(
                select(User).where(User.id == uuid.UUID(user_id_str))
            )).scalar_one_or_none()
            if not target_user:
                raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
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
        try:
            group_id = uuid.UUID(group_id_str)
        except (TypeError, ValueError):
            group_id = None
    else:
        role     = raw
        group_id = None

    # 4. Mavjud foydalanuvchini tekshirish
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        existing = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if existing:
            # Allaqachon ro'yxatdan o'tgan — token qaytaramiz
            await delete_invite(data.tenant_slug, code)
            if not existing.is_active:
                raise AuthAccountInactive()
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
        await session.flush()

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

    await delete_invite(data.tenant_slug, code)

    return ok({**(_make_tokens(user, data.tenant_slug)), "is_new_user": True, "role": role})
