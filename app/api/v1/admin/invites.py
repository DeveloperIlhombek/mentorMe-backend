"""
app/api/v1/admin/invites.py

Universal invite link generatsiyasi.
Admin istalgan rol uchun invite kodi yaratadi.

POST /invites/generate
  body: {role, group_id?, note?}
  return: {invite_code, deep_link, role, expires_hours}

Invite kodi formati: INV-XXXXXX (48 soat)
Storage: app.core.invite_store (Redis yoki in-memory)
"""
import random
import string
import uuid
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_tenant_session, require_admin
from app.core.invite_store import store_invite
from app.schemas import ok

router = APIRouter(prefix="/invites", tags=["invites"])

INVITE_TTL_HOURS = 48
VALID_ROLES = ("teacher", "inspector", "student", "parent")


class InviteGenerateBody(BaseModel):
    role:     Literal["teacher", "inspector", "student", "parent"]
    group_id: Optional[uuid.UUID] = None   # student uchun
    note:     Optional[str]       = None   # eslatma (ism yoki maqsad)


def _gen_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "INV-" + "".join(random.choices(chars, k=6))


@router.post("/generate")
async def generate_invite(
    body: InviteGenerateBody,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    """
    Admin uchun: istalgan rol uchun invite kodi yaratish.

    - teacher / inspector → Telegram orqali ro'yxatdan o'tadi
    - student            → guruh bilan birga
    - parent             → farzandga keyinchalik bog'lanadi
    """
    tenant_slug = tkn.get("tenant_slug", "default")

    # Student uchun guruh tekshiruvi
    if body.role == "student" and body.group_id:
        from app.models.tenant.group import Group
        group = (await db.execute(
            select(Group).where(Group.id == body.group_id)
        )).scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="Guruh topilmadi")

    code = _gen_code()

    # Saqlash — Redis yoki memory
    payload = body.role
    if body.role == "student" and body.group_id:
        payload = f"student:{body.group_id}"

    await store_invite(tenant_slug, code, payload)

    # Deep link
    bot_username = getattr(settings, "BOT_USERNAME", "edusaaasbot")
    deep_link    = (
        f"https://t.me/{bot_username}?startapp="
        f"inv_{tenant_slug}_{code}"
    )
    webapp_link  = (
        f"{settings.FRONTEND_URL.rstrip('/')}/uz/onboarding"
        f"?code={code}&tenant={tenant_slug}"
    )

    return ok({
        "invite_code":   code,
        "role":          body.role,
        "group_id":      str(body.group_id) if body.group_id else None,
        "deep_link":     deep_link,
        "webapp_link":   webapp_link,
        "tenant_slug":   tenant_slug,
        "expires_hours": INVITE_TTL_HOURS,
        "note":          body.note,
    })


@router.get("/info/{code}")
async def get_invite_info(
    code:       str,
    tenant:     str,
    db:         AsyncSession = Depends(get_tenant_session),
):
    """
    Invite kod haqida ma'lumot olish (login/onboarding sahifasida ishlatilinadi).
    Autentifikatsiya talab qilinmaydi.
    """
    from app.core.invite_store import get_invite

    raw = await get_invite(tenant, code)
    if not raw:
        raise HTTPException(status_code=404, detail="Kod topilmadi yoki muddati o'tgan")

    if ":" in raw:
        role, group_id_str = raw.split(":", 1)
        group_id = group_id_str
    else:
        role     = raw
        group_id = None

    # Guruh nomini olish
    group_name = None
    if group_id:
        from app.models.tenant.group import Group
        g = (await db.execute(
            select(Group).where(Group.id == uuid.UUID(group_id))
        )).scalar_one_or_none()
        if g:
            group_name = f"{g.name} ({g.subject})"

    return ok({
        "role":       role,
        "group_id":   group_id,
        "group_name": group_name,
        "valid":      True,
    })
