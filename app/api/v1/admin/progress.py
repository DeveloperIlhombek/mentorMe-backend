"""
app/api/v1/admin/progress.py
O'quvchi o'zlashtirish darajasini boshqarish (admin tomonidan).

Endpointlar:
  GET  /progress                  — barcha yozuvlar (filter bilan)
  GET  /progress/student/{id}     — bitta o'quvchining xulosasi (oy bo'yicha)
  POST /progress/generate         — oy uchun pending yozuvlar yaratish
  POST /progress/student/{id}/dates — o'quvchi uchun progress_dates belgilash
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_inspector
from app.schemas import ok
from app.services import student_progress as svc

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("")
async def list_progress(
    student_id: Optional[uuid.UUID] = Query(None),
    teacher_id: Optional[uuid.UUID] = Query(None),
    month:  Optional[int]           = Query(None),
    year:   Optional[int]           = Query(None),
    status: Optional[str]           = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_inspector),
):
    """O'zlashtirish yozuvlarini ko'rish (filtr bilan)."""
    return ok(await svc.get_progress(
        db,
        student_id=student_id,
        teacher_id=teacher_id,
        month=month,
        year=year,
        status=status,
    ))


@router.get("/student/{student_id}/summary")
async def student_progress_summary(
    student_id: uuid.UUID,
    month: int  = Query(...),
    year:  int  = Query(...),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),
):
    """Bitta o'quvchining bir oy bo'yicha qisqa xulosasi (avg_score, color, entries)."""
    return ok(await svc.get_student_progress_summary(db, student_id, month, year))


@router.post("/generate")
async def generate_schedules(
    month: int           = Query(..., ge=1, le=12),
    year:  int           = Query(..., ge=2024),
    student_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession     = Depends(get_tenant_session),
    _:  dict             = Depends(require_admin),
):
    """
    Berilgan oy uchun progress_dates bo'lgan barcha o'quvchilarga
    pending yozuvlar yaratadi (oy boshida cron job chaqirishi kerak).
    """
    created = await svc.generate_monthly_schedules(db, month, year, student_id)
    return ok({"created_count": len(created), "entries": created})


@router.post("/student/{student_id}/dates")
async def set_progress_dates(
    student_id: uuid.UUID,
    dates: List[int],
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'quvchi uchun oylik progress kiritish kunlarini belgilash (masalan: [15, 28])."""
    return ok(await svc.set_student_progress_dates(db, student_id, dates))
