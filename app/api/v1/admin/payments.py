"""
app/api/v1/admin/payments.py

To'lovlar endpointlari.
Faqat admin foydalanadi.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_inspector, get_optional_branch_filter
from app.schemas import PaymentCreate, ok
from app.services import payment as payment_svc

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("")
async def list_payments(
    page:       int                  = Query(1, ge=1),
    per_page:   int                  = Query(20, ge=1, le=100),
    student_id: Optional[uuid.UUID]  = Query(None),
    status:     Optional[str]        = Query(None),
    month:      Optional[int]        = Query(None, ge=1, le=12),
    year:       Optional[int]        = Query(None),
    db: AsyncSession                 = Depends(get_tenant_session),
    _:  dict                         = Depends(require_inspector),
    branch_filter: Optional[str]     = Depends(get_optional_branch_filter),
):
    """To'lovlar ro'yxati (filter, sahifalash)."""
    import uuid as _uuid
    branch_id_f = _uuid.UUID(branch_filter) if branch_filter else None
    payments, total = await payment_svc.get_payments(
        db, page=page, per_page=per_page,
        student_id=student_id, status=status,
        month=month, year=year,
        branch_id=branch_id_f,
    )
    pages = (total + per_page - 1) // per_page
    return ok(payments, {
        "page": page, "per_page": per_page,
        "total": total, "total_pages": pages,
    })


@router.post("", status_code=201)
async def create_payment(
    data: PaymentCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_inspector),
):
    """Naqd to'lov qo'shish (admin yoki inspektor tomonidan)."""
    result = await payment_svc.create_manual(
        db, data,
        received_by=uuid.UUID(tkn["sub"]),
    )
    return ok(result)


@router.get("/debtors")
async def get_debtors(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),
):
    """Manfiy balansli (qarzdor) o'quvchilar."""
    debtors = await payment_svc.get_debtors(db)
    return ok(debtors)
