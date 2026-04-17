"""app/services/finance.py — Moliya xizmatlari."""
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.finance import FinanceBalance, FinanceTransaction

# ─── Kategoriyalar ────────────────────────────────────────────────────
INCOME_CATEGORIES  = ["talaba_tolov", "grant", "boshqa_kirim"]
EXPENSE_CATEGORIES = ["ish_haqi", "ijara", "kommunal", "inventar",
                       "reklama", "soliq", "ta_mirlash", "boshqa_chiqim"]

CATEGORY_LABELS = {
    "talaba_tolov":  "Talaba to'lovi",
    "grant":         "Grant / subsidiya",
    "boshqa_kirim":  "Boshqa kirim",
    "ish_haqi":      "Ish haqi",
    "ijara":         "Ijara",
    "kommunal":      "Kommunal xarajat",
    "inventar":      "Inventar / jihozlar",
    "reklama":       "Reklama / marketing",
    "soliq":         "Soliq / davlat to'lovi",
    "ta_mirlash":    "Ta'mirlash",
    "boshqa_chiqim": "Boshqa chiqim",
}


async def get_balance(db: AsyncSession) -> dict:
    """Joriy kassa holati."""
    stmt = select(FinanceBalance)
    bal  = (await db.execute(stmt)).scalar_one_or_none()
    if not bal:
        bal = FinanceBalance()
        db.add(bal)
        await db.commit()
        await db.refresh(bal)
    return {
        "cash_amount":  float(bal.cash_amount),
        "bank_amount":  float(bal.bank_amount),
        "total_amount": float(bal.cash_amount + bal.bank_amount),
    }


async def _update_balance(db: AsyncSession, tx: FinanceTransaction) -> None:
    """Tranzaksiyadan keyin balansni yangilash."""
    stmt = select(FinanceBalance)
    bal  = (await db.execute(stmt)).scalar_one_or_none()
    if not bal:
        bal = FinanceBalance()
        db.add(bal)
        await db.flush()

    sign = Decimal("1") if tx.type == "income" else Decimal("-1")
    amt  = Decimal(str(tx.amount))

    if tx.payment_method == "cash":
        bal.cash_amount += sign * amt
    else:
        bal.bank_amount += sign * amt


async def create_transaction(
    db:             AsyncSession,
    type:           str,
    amount:         Decimal,
    category:       str,
    payment_method: str          = "cash",
    description:    Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id:   Optional[uuid.UUID] = None,
    created_by:     Optional[uuid.UUID] = None,
    transaction_date: Optional[date]    = None,
) -> dict:
    """Yangi tranzaksiya yaratish va balansni yangilash."""
    tx = FinanceTransaction(
        type             = type,
        amount           = amount,
        payment_method   = payment_method,
        category         = category,
        description      = description,
        reference_type   = reference_type,
        reference_id     = reference_id,
        created_by       = created_by,
        transaction_date = transaction_date or date.today(),
    )
    db.add(tx)
    await db.flush()
    await _update_balance(db, tx)
    await db.commit()
    await db.refresh(tx)
    return _tx_dict(tx)


async def get_transactions(
    db:         AsyncSession,
    page:       int  = 1,
    per_page:   int  = 20,
    type:       Optional[str] = None,
    category:   Optional[str] = None,
    method:     Optional[str] = None,
    month:      Optional[int] = None,
    year:       Optional[int] = None,
    date_from:  Optional[date] = None,
    date_to:    Optional[date] = None,
) -> Tuple[List[dict], int]:
    stmt = select(FinanceTransaction)

    if type:      stmt = stmt.where(FinanceTransaction.type == type)
    if category:  stmt = stmt.where(FinanceTransaction.category == category)
    if method:    stmt = stmt.where(FinanceTransaction.payment_method == method)
    if month:     stmt = stmt.where(extract("month", FinanceTransaction.transaction_date) == month)
    if year:      stmt = stmt.where(extract("year",  FinanceTransaction.transaction_date) == year)
    if date_from: stmt = stmt.where(FinanceTransaction.transaction_date >= date_from)
    if date_to:   stmt = stmt.where(FinanceTransaction.transaction_date <= date_to)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt  = stmt.order_by(desc(FinanceTransaction.transaction_date),
                          desc(FinanceTransaction.created_at))
    stmt  = stmt.offset((page - 1) * per_page).limit(per_page)
    rows  = (await db.execute(stmt)).scalars().all()
    return [_tx_dict(r) for r in rows], total


async def get_monthly_summary(
    db:    AsyncSession,
    month: int,
    year:  int,
) -> dict:
    """Oylik kirim-chiqim va kategoriya bo'yicha taqsimot."""
    stmt = select(
        FinanceTransaction.type,
        FinanceTransaction.category,
        FinanceTransaction.payment_method,
        func.sum(FinanceTransaction.amount).label("total"),
    ).where(
        and_(
            extract("month", FinanceTransaction.transaction_date) == month,
            extract("year",  FinanceTransaction.transaction_date) == year,
        )
    ).group_by(
        FinanceTransaction.type,
        FinanceTransaction.category,
        FinanceTransaction.payment_method,
    )
    rows = (await db.execute(stmt)).all()

    income_total  = sum(float(r.total) for r in rows if r.type == "income")
    expense_total = sum(float(r.total) for r in rows if r.type == "expense")

    by_category: dict = {}
    for r in rows:
        key = r.category
        if key not in by_category:
            by_category[key] = {"type": r.type, "total": 0.0,
                                 "label": CATEGORY_LABELS.get(key, key)}
        by_category[key]["total"] += float(r.total)

    # Oylik trend uchun kunlik ma'lumot
    daily_stmt = select(
        FinanceTransaction.transaction_date,
        FinanceTransaction.type,
        func.sum(FinanceTransaction.amount).label("total"),
    ).where(
        and_(
            extract("month", FinanceTransaction.transaction_date) == month,
            extract("year",  FinanceTransaction.transaction_date) == year,
        )
    ).group_by(
        FinanceTransaction.transaction_date,
        FinanceTransaction.type,
    ).order_by(FinanceTransaction.transaction_date)
    daily_rows = (await db.execute(daily_stmt)).all()

    daily: dict = {}
    for r in daily_rows:
        d = r.transaction_date.isoformat()
        if d not in daily:
            daily[d] = {"income": 0.0, "expense": 0.0}
        daily[d][r.type] += float(r.total)

    return {
        "month":         month,
        "year":          year,
        "income_total":  income_total,
        "expense_total": expense_total,
        "net":           income_total - expense_total,
        "by_category":   list(by_category.values()),
        "daily":         [{"date": d, **v} for d, v in daily.items()],
    }


async def delete_transaction(db: AsyncSession, tx_id: uuid.UUID) -> bool:
    """Tranzaksiyani o'chirish va balansni teskari yangilash."""
    stmt = select(FinanceTransaction).where(FinanceTransaction.id == tx_id)
    tx   = (await db.execute(stmt)).scalar_one_or_none()
    if not tx:
        return False
    # Teskari: income → chiqim, expense → kirim
    reverse_type = "expense" if tx.type == "income" else "income"
    reverse_tx   = FinanceTransaction(
        type=reverse_type, amount=tx.amount,
        payment_method=tx.payment_method, category="correction",
    )
    await _update_balance(db, reverse_tx)
    await db.delete(tx)
    await db.commit()
    return True


def _tx_dict(tx: FinanceTransaction) -> dict:
    return {
        "id":               str(tx.id),
        "type":             tx.type,
        "amount":           float(tx.amount),
        "currency":         tx.currency,
        "payment_method":   tx.payment_method,
        "category":         tx.category,
        "category_label":   CATEGORY_LABELS.get(tx.category, tx.category),
        "description":      tx.description,
        "reference_type":   tx.reference_type,
        "reference_id":     str(tx.reference_id) if tx.reference_id else None,
        "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
        "created_at":       tx.created_at.isoformat() if tx.created_at else None,
    }
