"""
app/api/v1/admin/lesson_cancellations.py
Dars bekor qilish va qo'shimcha dars endpointlari.
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_inspector, require_teacher
from app.schemas import ok
from app.services import lesson_cancellation as svc

router = APIRouter(prefix="/lesson-cancellations", tags=["lesson-cancellations"])


class CancelLessonBody(BaseModel):
    group_id:    uuid.UUID
    lesson_date: date
    scope:       str = "group"
    student_id:  Optional[uuid.UUID] = None
    reason:      Optional[str]       = None


class ExtraLessonBody(BaseModel):
    group_id:    uuid.UUID
    lesson_date: date
    scope:       str = "group"
    student_id:  Optional[uuid.UUID] = None
    reason:      Optional[str]       = None


@router.post("/cancel")
async def cancel_lesson(
    data: CancelLessonBody,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """Teacher → 'pending'. Admin/Inspektor → 'approved' (to'lov darhol o'zgaradi)."""
    result = await svc.cancel_lesson(
        db,
        group_id        = data.group_id,
        lesson_date     = data.lesson_date,
        scope           = data.scope,
        student_id      = data.student_id,
        reason          = data.reason,
        created_by      = uuid.UUID(tkn["sub"]),
        created_by_role = tkn.get("role", "teacher"),
    )
    return ok(result)


@router.post("/extra")
async def add_extra_lesson(
    data: ExtraLessonBody,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """Teacher → 'pending'. Admin/Inspektor → 'approved'."""
    result = await svc.add_extra_lesson(
        db,
        group_id        = data.group_id,
        lesson_date     = data.lesson_date,
        scope           = data.scope,
        student_id      = data.student_id,
        reason          = data.reason,
        created_by      = uuid.UUID(tkn["sub"]),
        created_by_role = tkn.get("role", "teacher"),
    )
    return ok(result)


@router.get("/pending")
async def list_pending(
    group_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession              = Depends(get_tenant_session),
    _:  dict                      = Depends(require_inspector),
):
    """Admin/Inspektor: kutilayotgan dars so'rovlari."""
    return ok(await svc.list_pending(db, group_id=group_id))


@router.get("")
async def list_cancellations(
    group_id:   Optional[uuid.UUID] = Query(None),
    student_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_teacher),
):
    """Barcha dars o'zgarishlari ro'yxati."""
    return ok(await svc.get_cancellations(db, group_id=group_id, student_id=student_id))


@router.get("/adjustments")
async def list_adjustments(
    student_id: Optional[uuid.UUID] = Query(None),
    group_id:   Optional[uuid.UUID] = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_teacher),
):
    """To'lov korreksiyalari."""
    return ok(await svc.get_adjustments(db, student_id=student_id, group_id=group_id))


@router.patch("/{cancellation_id}/approve")
async def approve_cancellation(
    cancellation_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_inspector),
):
    """Admin/Inspektor: so'rovni tasdiqlash → to'lov o'zgartiriladi."""
    result = await svc.approve_cancellation(
        db,
        cancellation_id = cancellation_id,
        reviewed_by     = uuid.UUID(tkn["sub"]),
    )
    return ok(result)


@router.patch("/{cancellation_id}/reject")
async def reject_cancellation(
    cancellation_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_inspector),
):
    """Admin/Inspektor: so'rovni rad etish."""
    result = await svc.reject_cancellation(
        db,
        cancellation_id = cancellation_id,
        reviewed_by     = uuid.UUID(tkn["sub"]),
    )
    return ok(result)
