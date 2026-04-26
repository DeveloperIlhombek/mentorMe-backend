"""
app/api/v1/parent.py

Ota-ona paneli endpointlari:
  GET  /parent/children                      — farzandlar ro'yxati
  GET  /parent/children/{student_id}/attendance
  GET  /parent/children/{student_id}/payments
  POST /parent/link-invite                   — invite kodi orqali farzandga bog'lanish
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_parent
from app.core.invite_store import get_invite, delete_invite
from app.models.tenant import Student, User
from app.schemas import ok
from app.services import attendance as att_svc
from app.services import payment as payment_svc

router = APIRouter(prefix="/parent", tags=["parent"])


async def _get_children(db: AsyncSession, parent_user_id: uuid.UUID):
    """Ota-onaning farzandlari."""
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.parent_id == parent_user_id)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id":         str(s.id),
            "user_id":    str(s.user_id),
            "first_name": u.first_name,
            "last_name":  u.last_name,
            "balance":    float(s.balance),
            "is_active":  s.is_active,
        }
        for s, u in rows
    ]


@router.get("/children")
async def get_children(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_parent),
):
    """Farzandlar ro'yxati."""
    parent_id = uuid.UUID(tkn["sub"])
    children  = await _get_children(db, parent_id)
    return ok(children)


@router.get("/children/{student_id}/attendance")
async def get_child_attendance(
    student_id: uuid.UUID,
    month: Optional[int] = Query(None, ge=1, le=12),
    year:  Optional[int] = Query(None),
    db:    AsyncSession  = Depends(get_tenant_session),
    tkn:   dict          = Depends(require_parent),
):
    """Farzandning davomati."""
    result = await att_svc.get_student_history(db, student_id, month, year)
    return ok(result)


@router.get("/children/{student_id}/assessment")
async def get_child_assessment(
    student_id: uuid.UUID,
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db:    AsyncSession  = Depends(get_tenant_session),
    _:     dict          = Depends(require_parent),
):
    """Farzandning oylik baholash natijalari."""
    from app.services import student_progress as svc
    scores = await svc.get_student_scores(db, student_id, month, year)
    return ok(scores)


@router.get("/children/{student_id}/payments")
async def get_child_payments(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_parent),
):
    """Farzandning to'lov tarixi."""
    payments, total = await payment_svc.get_payments(db, student_id=student_id)
    return ok(payments, {"total": total})


# ── Invite code orqali farzandga bog'lanish ───────────────────────────

class LinkInviteBody(BaseModel):
    invite_code: str  # "PRN-XXXX" format


@router.post("/link-invite")
async def link_invite(
    body: LinkInviteBody,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_parent),
):
    """
    Ota-ona invite kodi orqali farzandga bog'lanadi.
    Kod admin tomonidan /students/{id}/generate-parent-link orqali generatsiya qilingan.
    """
    parent_user_id = uuid.UUID(tkn["sub"])
    tenant_slug    = tkn.get("tenant_slug", "default")
    code           = body.invite_code.strip().upper()

    # Kodni olish (Redis yoki in-memory fallback)
    stored_value = await get_invite(tenant_slug, code)
    if not stored_value:
        raise HTTPException(status_code=404, detail="Kod topilmadi yoki muddati o'tgan")

    # stored_value: UUID string (parent linking) yoki "role:uuid" (universal invite)
    # Parent linking uchun — faqat UUID
    try:
        student_id = uuid.UUID(stored_value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Bu kod parent linking uchun emas. PRN-XXXXXX formatidagi kod kiriting."
        )

    # Studentni topish
    stmt    = select(Student).where(Student.id == student_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi")

    # Ota-onaning o'zi users jadvalida borligini tekshirish
    parent_stmt = select(User).where(User.id == parent_user_id)
    parent_user = (await db.execute(parent_stmt)).scalar_one_or_none()
    if not parent_user:
        raise HTTPException(status_code=404, detail="Ota-ona foydalanuvchisi topilmadi")

    # Ota-onani bog'lash
    student.parent_id = parent_user_id
    await db.commit()
    await db.refresh(student)

    # Kodni o'chirish (bir martalik)
    await delete_invite(tenant_slug, code)

    # Farzand ma'lumotlarini qaytarish
    user_stmt = select(User).where(User.id == student.user_id)
    user      = (await db.execute(user_stmt)).scalar_one_or_none()

    return ok({
        "student_id":   str(student.id),
        "first_name":   user.first_name if user else "",
        "last_name":    user.last_name  if user else "",
        "balance":      float(student.balance),
        "message":      "Muvaffaqiyatli bog'landi!",
    })
