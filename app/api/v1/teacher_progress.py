"""
app/api/v1/teacher_progress.py
O'qituvchi tomonidan o'zlashtirish darajasini kiritish.

Endpointlar:
  GET  /teacher/progress          — o'qituvchining pending yozuvlari
  POST /teacher/progress/{id}     — score kiritish
  GET  /teacher/progress/summary  — o'quvchi xulosasi
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_teacher
from app.models.tenant.teacher import Teacher
from app.models.tenant.user import User
from app.schemas import ok
from app.services import student_progress as svc
from sqlalchemy import select

router = APIRouter(prefix="/teacher/progress", tags=["teacher-progress"])


class ProgressSubmit(BaseModel):
    score: float = Field(..., ge=0, le=100, description="O'zlashtirish darajasi (0-100%)")
    notes: Optional[str] = None


@router.get("")
async def my_pending_progress(
    month:  Optional[int] = Query(None),
    year:   Optional[int] = Query(None),
    status: str           = Query("pending"),
    db: AsyncSession      = Depends(get_tenant_session),
    tkn: dict             = Depends(require_teacher),
):
    """O'qituvchining kiritishi kerak bo'lgan (yoki kiritilgan) progress yozuvlari."""
    teacher = await _get_teacher(db, uuid.UUID(tkn["sub"]))
    if not teacher:
        return ok([])
    return ok(await svc.get_progress(
        db, teacher_id=teacher.id, month=month, year=year, status=status
    ))


@router.post("/{progress_id}")
async def submit_score(
    progress_id: uuid.UUID,
    data: ProgressSubmit,
    db: AsyncSession = Depends(get_tenant_session),
    tkn: dict        = Depends(require_teacher),
):
    """O'qituvchi o'quvchining o'zlashtirish darajasini kiritadi."""
    submitted_by = uuid.UUID(tkn["sub"])
    result = await svc.submit_progress(
        db,
        progress_id  = progress_id,
        score        = data.score,
        notes        = data.notes,
        submitted_by = submitted_by,
    )
    return ok(result)


@router.get("/student/{student_id}/summary")
async def student_summary(
    student_id: uuid.UUID,
    month: int  = Query(...),
    year:  int  = Query(...),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """O'quvchining bitta oy bo'yicha o'zlashtirish xulosasi."""
    return ok(await svc.get_student_progress_summary(db, student_id, month, year))


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID):
    t = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id)
    )).scalar_one_or_none()
    return t
