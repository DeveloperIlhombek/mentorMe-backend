"""
app/api/v1/admin/assessment.py
Admin: baholash deadline sozlash va monitoring.

  PATCH /admin/assessment/groups/{group_id}/deadline   — deadline belgilash
  GET   /admin/assessment/status?month=&year=           — barcha o'qituvchilar holati
  GET   /admin/assessment/teacher/{teacher_id}?month=&year= — bitta o'qituvchi
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_inspector
from app.schemas import ok
from app.services import student_progress as svc

router = APIRouter(prefix="/admin/assessment", tags=["admin-assessment"])


class DeadlineBody(BaseModel):
    deadline_day:  int = Field(..., ge=1,  le=28)
    deadline_hour: int = Field(..., ge=0,  le=23)


@router.patch("/groups/{group_id}/deadline")
async def set_deadline(
    group_id: uuid.UUID,
    body: DeadlineBody,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_inspector),
):
    """Admin/Inspektor: guruh uchun baholash deadline ni belgilaydi."""
    result = await svc.set_group_deadline(
        db, group_id, body.deadline_day, body.deadline_hour
    )
    return ok(result)


@router.get("/status")
async def all_teachers_status(
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db:  AsyncSession    = Depends(get_tenant_session),
    _:   dict            = Depends(require_inspector),
):
    """Barcha o'qituvchilarning baholash holati."""
    today = date.today()
    m = month or today.month
    y = year  or today.year
    data = await svc.get_all_teachers_assessment_status(db, m, y)
    return ok(data)


@router.get("/teacher/{teacher_id}")
async def teacher_assessment(
    teacher_id: uuid.UUID,
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db:  AsyncSession    = Depends(get_tenant_session),
    _:   dict            = Depends(require_inspector),
):
    """Bitta o'qituvchining baholash holati."""
    today = date.today()
    m = month or today.month
    y = year  or today.year
    data = await svc.get_teacher_assessments(db, teacher_id, m, y)
    return ok(data)
