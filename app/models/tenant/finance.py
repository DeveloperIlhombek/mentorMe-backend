"""app/models/tenant/finance.py"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type             = Column(String(10),  nullable=False)          # income | expense
    amount           = Column(Numeric(15, 2), nullable=False)
    currency         = Column(String(5),   nullable=False, default="UZS")
    payment_method   = Column(String(20),  nullable=False, default="cash")  # cash | bank
    category         = Column(String(50),  nullable=False)
    description      = Column(Text)
    reference_type   = Column(String(30))                           # payment | salary | ...
    reference_id     = Column(UUID(as_uuid=True))
    created_by       = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    transaction_date = Column(Date, nullable=False, default=date.today)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("type IN ('income','expense')", name="ck_finance_type"),
        CheckConstraint("payment_method IN ('cash','bank')", name="ck_finance_method"),
        CheckConstraint("amount > 0", name="ck_finance_amount"),
    )


class FinanceBalance(Base):
    __tablename__ = "finance_balance"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cash_amount = Column(Numeric(15, 2), nullable=False, default=0)
    bank_amount = Column(Numeric(15, 2), nullable=False, default=0)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
