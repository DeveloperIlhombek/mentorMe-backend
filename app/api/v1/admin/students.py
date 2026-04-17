"""
app/api/v1/admin/students.py
O'quvchilar boshqaruvi endpointlari.

Ruxsatlar:
  require_inspector → admin + inspektor
  require_admin     → faqat admin
  require_teacher   → admin + inspektor + o'qituvchi
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
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
from app.services import student as student_svc

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
    tkn:  dict         = Depends(require_inspector),   # inspektor ham qo'sha oladi
):
    result = await student_svc.create(
        db, data,
        created_by=uuid.UUID(tkn["sub"]),
    )
    return ok(result)


# ── Admin-only: tasdiq jarayoni ──────────────────────────────────────

@router.get("/pending-approval")
async def pending_approval(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    students, total = await student_svc.get_students(
        db, page=1, per_page=100, is_active=False
    )
    pending = [s for s in students if not s.get("is_approved", True)]
    return ok(pending, {"total": len(pending)})


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


@router.delete("/{student_id}", status_code=204)
async def delete_student(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),         # o'chirish faqat admin
):
    await student_svc.soft_delete(db, student_id)


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
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),        # admin tasdiqlaydi
):
    await student_svc.soft_delete(db, student_id)
    return ok({"message": "O'quvchi o'chirildi"})


@router.post("/{student_id}/groups/{group_id}", status_code=201)
async def add_to_group(
    student_id: uuid.UUID,
    group_id:   uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),     # inspektor ham qo'shadi
):
    result = await student_svc.add_to_group(db, student_id, group_id)
    return ok(result)


@router.delete("/{student_id}/groups/{group_id}", status_code=204)
async def remove_from_group(
    student_id: uuid.UUID,
    group_id:   uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),     # inspektor ham chiqaradi
):
    await student_svc.remove_from_group(db, student_id, group_id)


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


@router.post("/{student_id}/link-parent")
async def link_parent(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),        # ota-ona bog'lash — admin
):
    return ok({"message": "Ota-ona bog'lash"})
