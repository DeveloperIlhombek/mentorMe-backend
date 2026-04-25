"""
app/api/v1/admin/lesson_cancellations.py
Dars bekor qilish va qo'shimcha dars endpointlari.

Endpointlar:
  POST /lesson-cancellations/cancel     — dars bekor qilish
  POST /lesson-cancellations/extra      — qo'shimcha dars qo'shish
  GET  /lesson-cancellations            — bekor qilishlar ro'yxati
  GET  /lesson-cancellations/adjustments — to'lov korreksiyalari
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_inspector
from app.schemas import ok
from app.services import lesson_cancellation as svc

router = APIRouter(prefix="/lesson-cancellations", tags=["lesson-cancellations"])


class CancelLessonBody(BaseModel):
    group_id:    uuid.UUID
    lesson_date: date
    scope:       str = "group"          # 'group' | 'student'
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
    tkn:  dict         = Depends(require_inspector),
):
    """
    Darsni bekor qilish.
    scope='group'   → guruhning barcha o'quvchilari payment_day uzayadi.
    scope='student' → faqat tanlangan o'quvchi payment_day uzayadi.
    """
    result = await svc.cancel_lesson(
        db,
        group_id    = data.group_id,
        lesson_date = data.lesson_date,
        scope       = data.scope,
        student_id  = data.student_id,
        reason      = data.reason,
        created_by  = uuid.UUID(tkn["sub"]),
    )
    return ok(result)


@router.post("/extra")
async def add_extra_lesson(
    data: ExtraLessonBody,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_inspector),
):
    """
    Qo'shimcha dars qo'shish.
    O'quvchining keyingi to'lov sanasi qisqaradi (debit korreksiya).
    """
    result = await svc.add_extra_lesson(
        db,
        group_id    = data.group_id,
        lesson_date = data.lesson_date,
        scope       = data.scope,
        student_id  = data.student_id,
        reason      = data.reason,
        created_by  = uuid.UUID(tkn["sub"]),
    )
    return ok(result)


@router.get("")
async def list_cancellations(
    group_id:   Optional[uuid.UUID] = Query(None),
    student_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_inspector),
):
    """Bekor qilingan darslar ro'yxati."""
    return ok(await svc.get_cancellations(db, group_id=group_id, student_id=student_id))


@router.get("/adjustments")
async def list_adjustments(
    student_id: Optional[uuid.UUID] = Query(None),
    group_id:   Optional[uuid.UUID] = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_inspector),
):
    """To'lov korreksiyalari ro'yxati (credit va debit)."""
    return ok(await svc.get_adjustments(db, student_id=student_id, group_id=group_id))
