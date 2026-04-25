"""
app/api/v1/admin/students.py
O'quvchilar boshqaruvi endpointlari.

Ruxsatlar:
  require_inspector → admin + inspektor
  require_admin     → faqat admin
  require_teacher   → admin + inspektor + o'qituvchi
"""
import random
import string
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_tenant_session,
    require_admin,
    require_inspector,
    require_teacher,
    get_optional_branch_filter,
)
from app.core.exceptions import StudentNotFound
from app.models.tenant import Notification
from app.models.tenant.student import Student
from app.models.tenant.user import User
from app.schemas import StudentCreate, StudentUpdate, ok
from app.schemas.student import StudentDeactivate
from app.services import student as student_svc
from app.services.student import _get_student_groups

router = APIRouter(prefix="/students", tags=["students"])


@router.get("")
async def list_students(
    page:      int                 = Query(1, ge=1),
    per_page:  int                 = Query(20, ge=1, le=500),
    search:    Optional[str]       = Query(None),
    group_id:  Optional[uuid.UUID] = Query(None),
    is_active: Optional[bool]      = Query(None),
    db: AsyncSession               = Depends(get_tenant_session),
    _:  dict                       = Depends(require_teacher),
    branch_filter: Optional[str]   = Depends(get_optional_branch_filter),
):
    branch_id_filter = uuid.UUID(branch_filter) if branch_filter else None
    students, total = await student_svc.get_students(
        db, page=page, per_page=per_page,
        search=search, group_id=group_id, is_active=is_active,
        branch_id=branch_id_filter,
    )
    pages = (total + per_page - 1) // per_page
    return ok(students, {"page": page, "per_page": per_page,
                         "total": total, "total_pages": pages})


@router.post("", status_code=201)
async def create_student(
    data: StudentCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),   # teacher ham qo'sha oladi (pending bo'ladi)
):
    caller_role = tkn.get("role", "teacher")
    result = await student_svc.create(
        db, data,
        created_by=uuid.UUID(tkn["sub"]),
        role=caller_role,
    )
    pending = not result.get("is_approved", True)
    return ok(result, {"pending_approval": pending})


# ── Admin-only: tasdiq jarayoni ──────────────────────────────────────

@router.get("/pending-approval")
async def pending_approval(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),  # inspektor ham ko'ra oladi
):
    """Tasdiqlanmagan o'quvchilar — is_approved=False va is_rejected=False."""
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.is_approved == False)
        .where(Student.is_rejected == False)
        .order_by(Student.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    result = []
    for student, user in rows:
        groups = await _get_student_groups(db, student.id)
        result.append({
            "id":                str(student.id),
            "user_id":           str(student.user_id),
            "first_name":        user.first_name,
            "last_name":         user.last_name,
            "phone":             user.phone,
            "email":             user.email,
            "is_active":         student.is_active,
            "is_approved":       student.is_approved,
            "is_rejected":       student.is_rejected,
            "pending_delete":    student.pending_delete,
            "pending_group_ids": student.pending_group_ids or [],
            "balance":           float(student.balance),
            "created_by":        str(student.created_by) if student.created_by else None,
            "groups":            groups,
        })

    return ok(result, {"total": len(result)})


@router.post("/{student_id}/approve")
async def approve_student(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    result = await student_svc.approve(db, student_id, approved_by=uuid.UUID(tkn["sub"]))
    return ok(result)


@router.post("/{student_id}/reject")
async def reject_student(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),
):
    result = await student_svc.reject(db, student_id)
    return ok(result)


@router.get("/{student_id}")
async def get_student(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    result = await student_svc.get_by_id(db, student_id)
    if not result:
        raise StudentNotFound()
    return ok(result)


@router.patch("/{student_id}")
async def update_student(
    student_id: uuid.UUID,
    data: StudentUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_inspector),   # inspektor ham yangilaydi
):
    result = await student_svc.update(db, student_id, data)
    return ok(result)


@router.delete("/{student_id}", status_code=200)
async def delete_student(
    student_id:   uuid.UUID,
    leave_reason: Optional[str]       = Query(None),
    churn_teacher_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'quvchini o'chirish — sabab va churn_teacher_id bilan."""
    await student_svc.soft_delete(
        db, student_id,
        leave_reason=leave_reason,
        churn_teacher_id=churn_teacher_id,
    )
    return ok({"message": "O'quvchi arxivlandi"})


@router.post("/{student_id}/request-delete")
async def request_delete_student(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_inspector),    # inspektor o'chirish so'raydi
):
    result = await student_svc.request_delete(db, student_id, requested_by=uuid.UUID(tkn["sub"]))
    return ok(result)


@router.post("/{student_id}/confirm-delete")
async def confirm_delete_student(
    student_id: uuid.UUID,
    data: StudentDeactivate,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),
):
    """Admin tasdiqlaydi — sabab va churn_teacher_id bilan."""
    await student_svc.soft_delete(
        db, student_id,
        leave_reason=data.leave_reason,
        churn_teacher_id=data.churn_teacher_id,
        notes=data.notes,
    )
    return ok({"message": "O'quvchi o'chirildi"})


@router.post("/{student_id}/groups/{group_id}", status_code=201)
async def add_to_group(
    student_id: uuid.UUID,
    group_id:   uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_inspector),     # inspektor ham qo'shadi
):
    from app.models.tenant.group import Group
    result = await student_svc.add_to_group(db, student_id, group_id)

    # Bildirishnoma: admin + inspektorlarga
    try:
        from bot.utils.notify import notify_group_enrollment
        student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
        group   = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
        caller  = (await db.execute(select(User).where(User.id == uuid.UUID(tkn["sub"])))).scalar_one_or_none()
        if student and group:
            student_user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
            s_name = f"{student_user.first_name} {student_user.last_name or ''}".strip() if student_user else "O'quvchi"
            c_name = f"{caller.first_name} {caller.last_name or ''}".strip() if caller else ""
            import asyncio
            asyncio.create_task(notify_group_enrollment(
                tenant_schema=tkn.get("tenant_slug", "default"),
                student_name=s_name,
                group_name=group.name,
                action="added",
                by_name=c_name,
                by_role=tkn.get("role", ""),
            ))
    except Exception:
        pass

    return ok(result)


@router.delete("/{student_id}/groups/{group_id}", status_code=204)
async def remove_from_group(
    student_id: uuid.UUID,
    group_id:   uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_inspector),     # inspektor ham chiqaradi
):
    from app.models.tenant.group import Group
    await student_svc.remove_from_group(db, student_id, group_id)

    # Bildirishnoma
    try:
        from bot.utils.notify import notify_group_enrollment
        student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
        group   = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
        caller  = (await db.execute(select(User).where(User.id == uuid.UUID(tkn["sub"])))).scalar_one_or_none()
        if student and group:
            student_user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
            s_name = f"{student_user.first_name} {student_user.last_name or ''}".strip() if student_user else "O'quvchi"
            c_name = f"{caller.first_name} {caller.last_name or ''}".strip() if caller else ""
            import asyncio
            asyncio.create_task(notify_group_enrollment(
                tenant_schema=tkn.get("tenant_slug", "default"),
                student_name=s_name,
                group_name=group.name,
                action="removed",
                by_name=c_name,
                by_role=tkn.get("role", ""),
            ))
    except Exception:
        pass


@router.get("/{student_id}/attendance")
async def student_attendance(
    student_id: uuid.UUID,
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db: AsyncSession     = Depends(get_tenant_session),
    _:  dict             = Depends(require_teacher),
):
    from app.services.attendance import get_student_history
    result = await get_student_history(db, student_id, month, year)
    return ok(result)


@router.get("/{student_id}/gamification")
async def student_gamification(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    from app.services.gamification import get_profile
    result = await get_profile(db, student_id)
    return ok(result)


@router.get("/{student_id}/payments")
async def student_payments(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    from app.services.payment import get_payments
    payments, _ = await get_payments(db, student_id=student_id, per_page=100)
    return ok(payments)


@router.post("/{student_id}/generate-parent-link")
async def generate_parent_link(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    """
    Admin uchun: O'quvchi uchun ota-ona invite kodi va deep link generatsiya qilish.
    Kod 48 soat saqlanadi (Redis mavjud bo'lsa — Redis'da, aks holda — in-memory).
    """
    from app.core.config import settings
    from app.core.invite_store import store_invite

    # O'quvchini tekshirish
    stmt = select(Student, User).join(User, Student.user_id == User.id).where(Student.id == student_id)
    row  = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi")
    student, user = row

    tenant_slug = tkn.get("tenant_slug", "default")

    # Invite kodi generatsiya (PRN-XXXXXX)
    code = "PRN-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    # Saqlash (Redis yoki in-memory fallback)
    await store_invite(tenant_slug, code, str(student_id))

    bot_username = getattr(settings, "BOT_USERNAME", "edusaasbot")
    deep_link    = f"https://t.me/{bot_username}?start=parent_{student_id}_{code}"

    return ok({
        "invite_code":   code,
        "deep_link":     deep_link,
        "student_id":    str(student_id),
        "student_name":  f"{user.first_name} {user.last_name or ''}".strip(),
        "expires_hours": 48,
    })


@router.post("/{student_id}/link-parent")
async def link_parent(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),
):
    """Eski endpoint — generate-parent-link ishlatilsin."""
    return ok({"message": "Eski endpoint. /generate-parent-link ishlatilsin."})


@router.post("/{student_id}/generate-invite")
async def generate_student_invite(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_inspector),
):
    """
    O'quvchi uchun Telegram aktivatsiya havolasi yaratish.
    O'quvchi bu link orqali botga kirib Telegram profilini bog'laydi.
    Payload: user_link:{user_id}
    """
    from app.core.config import settings
    from app.core.invite_store import store_invite

    stmt = select(Student, User).join(User, Student.user_id == User.id).where(Student.id == student_id)
    row  = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi")
    student, user = row

    tenant_slug = tkn.get("tenant_slug", "default")
    code = "STU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    await store_invite(tenant_slug, code, f"user_link:{str(user.id)}")

    bot_username = getattr(settings, "BOT_USERNAME", "edusaasbot")
    deep_link    = f"https://t.me/{bot_username}?startapp=inv_{tenant_slug}_{code}"
    webapp_link  = f"{settings.FRONTEND_URL.rstrip('/')}/uz/onboarding?code={code}&tenant={tenant_slug}"

    return ok({
        "invite_code":   code,
        "deep_link":     deep_link,
        "webapp_link":   webapp_link,
        "student_id":    str(student_id),
        "student_name":  f"{user.first_name} {user.last_name or ''}".strip(),
        "expires_hours": 48,
    })
