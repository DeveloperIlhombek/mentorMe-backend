"""app/api/v1/admin/finance.py — Moliya endpointlari."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_teacher
from app.schemas import ok
from app.services import finance as fin_svc

router = APIRouter(prefix="/finance", tags=["finance"])


class TransactionCreate(BaseModel):
    type:             str
    amount:           float
    category:         str
    payment_method:   str          = "cash"
    description:      Optional[str] = None
    transaction_date: Optional[date] = None

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in ("income", "expense"):
            raise ValueError("type must be 'income' or 'expense'")
        return v

    @field_validator("payment_method")
    @classmethod
    def check_method(cls, v: str) -> str:
        if v not in ("cash", "bank"):
            raise ValueError("payment_method must be 'cash' or 'bank'")
        return v

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v


@router.get("/balance")
async def get_balance(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """Kassa holati: naqd + bank + jami."""
    return ok(await fin_svc.get_balance(db))


@router.get("/transactions")
async def list_transactions(
    page:      int           = Query(1, ge=1),
    per_page:  int           = Query(20, ge=1, le=100),
    type:      Optional[str] = Query(None, description="income | expense"),
    category:  Optional[str] = Query(None),
    method:    Optional[str] = Query(None, description="cash | bank"),
    month:     Optional[int] = Query(None, ge=1, le=12),
    year:      Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db: AsyncSession          = Depends(get_tenant_session),
    _:  dict                  = Depends(require_teacher),
):
    """Tranzaksiyalar ro'yxati (filter + sahifalash)."""
    txs, total = await fin_svc.get_transactions(
        db, page=page, per_page=per_page,
        type=type, category=category, method=method,
        month=month, year=year, date_from=date_from, date_to=date_to,
    )
    pages = (total + per_page - 1) // per_page
    return ok(txs, {"page": page, "per_page": per_page, "total": total, "total_pages": pages})


@router.post("/transactions", status_code=201)
async def create_transaction(
    data: TransactionCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    """Yangi tranzaksiya yaratish."""
    tx = await fin_svc.create_transaction(
        db,
        type             = data.type,
        amount           = Decimal(str(data.amount)),
        category         = data.category,
        payment_method   = data.payment_method,
        description      = data.description,
        created_by       = uuid.UUID(tkn["sub"]),
        transaction_date = data.transaction_date,
    )
    return ok(tx)


@router.delete("/transactions/{tx_id}", status_code=200)
async def delete_transaction(
    tx_id: uuid.UUID,
    db:    AsyncSession = Depends(get_tenant_session),
    _:     dict         = Depends(require_admin),
):
    """Tranzaksiyani o'chirish (balans teskari yangilanadi)."""
    ok_flag = await fin_svc.delete_transaction(db, tx_id)
    if not ok_flag:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "TX_NOT_FOUND", "Tranzaksiya topilmadi")
    return ok({"message": "O'chirildi"})


@router.get("/summary")
async def monthly_summary(
    month: int = Query(..., ge=1, le=12),
    year:  int = Query(..., ge=2020),
    db:    AsyncSession = Depends(get_tenant_session),
    _:     dict         = Depends(require_teacher),
):
    """Oylik kirim-chiqim xulosasi + kategoriya taqsimoti + kunlik trend."""
    return ok(await fin_svc.get_monthly_summary(db, month, year))


@router.get("/categories")
async def get_categories(
    _: dict = Depends(require_teacher),
):
    """Mavjud kategoriyalar ro'yxati."""
    return ok({
        "income":  [{"slug": k, "label": v} for k, v in fin_svc.CATEGORY_LABELS.items()
                    if k in fin_svc.INCOME_CATEGORIES],
        "expense": [{"slug": k, "label": v} for k, v in fin_svc.CATEGORY_LABELS.items()
                    if k in fin_svc.EXPENSE_CATEGORIES],
    })
