"""
app/api/v1/admin/reports.py

Hisobot endpointlari:
  GET /reports/financial   — oylik moliyaviy hisobot (Excel)
  GET /reports/attendance  — davomat hisoboti (Excel)
  GET /reports/debtors     — qarzdorlar ro'yxati (Excel)
  GET /reports/salary      — o'qituvchi ish haqi (Excel)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_inspector
from app.services.report import (
    attendance_report, debtors_report,
    financial_report, teacher_salary_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/financial")
async def get_financial_report(
    month:     int                  = Query(..., ge=1, le=12),
    year:      int                  = Query(..., ge=2020),
    branch_id: Optional[uuid.UUID]  = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_inspector),
):
    """Oylik moliyaviy hisobot — Excel yuklab olish."""
    data = await financial_report(db, month, year, branch_id=branch_id)
    fname = f"financial_{year}_{month:02d}.xlsx"
    return Response(
        content=data,
        media_type=EXCEL_MIME,
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/attendance")
async def get_attendance_report(
    month:     int                  = Query(..., ge=1, le=12),
    year:      int                  = Query(..., ge=2020),
    group_id:  Optional[uuid.UUID]  = Query(None),
    branch_id: Optional[uuid.UUID]  = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_inspector),
):
    """Oylik davomat hisoboti — Excel."""
    data = await attendance_report(db, month, year, group_id, branch_id=branch_id)
    fname = f"attendance_{year}_{month:02d}.xlsx"
    return Response(
        content=data,
        media_type=EXCEL_MIME,
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/debtors")
async def get_debtors_report(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Qarzdorlar ro'yxati — Excel."""
    data = await debtors_report(db)
    return Response(
        content=data,
        media_type=EXCEL_MIME,
        headers={"Content-Disposition": "attachment; filename=debtors.xlsx"},
    )


@router.get("/salary")
async def get_salary_report(
    month: int = Query(..., ge=1, le=12),
    year:  int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'qituvchilar ish haqi hisoboti — Excel."""
    data = await teacher_salary_report(db, month, year)
    return Response(
        content=data,
        media_type=EXCEL_MIME,
        headers={"Content-Disposition": f"attachment; filename=salary_{year}_{month:02d}.xlsx"},
    )
