"""
app/api/v1/teacher_progress.py
O'qituvchi oylik baholash endpointlari.

  GET  /teacher/assessment/groups/{group_id}?month=&year=  — guruh baholash holati
  POST /teacher/assessment/groups/{group_id}/submit         — bulk score kiritish
  GET  /teacher/assessment/my?month=&year=                  — o'qituvchi KPI uchun holat
"""
import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_tenant_session, require_teacher
from app.models.tenant.teacher import Teacher
from app.schemas import ok
from app.services import student_progress as svc

router = APIRouter(prefix="/teacher/assessment", tags=["teacher-assessment"])


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID) -> Optional[Teacher]:
    return (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id)
    )).scalar_one_or_none()


class ScoreEntry(BaseModel):
    student_id: uuid.UUID
    score:      float = Field(..., ge=0, le=100)
    notes:      Optional[str] = None


class BulkSubmitBody(BaseModel):
    month:  int
    year:   int
    scores: List[ScoreEntry]


# ── Guruh baholash holati ─────────────────────────────────────────────

@router.get("/groups/{group_id}")
async def get_group_assessment(
    group_id: uuid.UUID,
    month: int = Query(default=None),
    year:  int = Query(default=None),
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_teacher),
):
    """Guruhning joriy oy baholash holati + barcha o'quvchilar."""
    today = date.today()
    m = month or today.month
    y = year  or today.year
    data = await svc.get_group_assessment(db, group_id, m, y)
    return ok(data)


# ── Bulk score kiritish ───────────────────────────────────────────────

@router.post("/groups/{group_id}/submit")
async def bulk_submit(
    group_id: uuid.UUID,
    body: BulkSubmitBody,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """Guruh o'quvchilari uchun baholashni bir vaqtda saqlash."""
    teacher = await _get_teacher(db, uuid.UUID(tkn["sub"]))
    if not teacher:
        from fastapi import HTTPException
        raise HTTPException(403, "Teacher topilmadi")

    scores = [{"student_id": str(e.student_id), "score": e.score, "notes": e.notes}
              for e in body.scores]
    result = await svc.bulk_submit_assessment(
        db,
        group_id   = group_id,
        month      = body.month,
        year       = body.year,
        teacher_id = teacher.id,
        scores     = scores,
    )
    return ok(result)


# ── O'qituvchi o'z baholash holati (KPI uchun) ────────────────────────

@router.get("/my")
async def my_assessment_status(
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db:  AsyncSession    = Depends(get_tenant_session),
    tkn: dict            = Depends(require_teacher),
):
    """O'qituvchining barcha guruhlari bo'yicha baholash holati."""
    teacher = await _get_teacher(db, uuid.UUID(tkn["sub"]))
    if not teacher:
        return ok({"groups": [], "total_submitted": 0, "total_students": 0})
    today = date.today()
    m = month or today.month
    y = year  or today.year
    data = await svc.get_teacher_assessments(db, teacher.id, m, y)
    return ok(data)
