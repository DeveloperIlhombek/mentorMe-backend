"""
app/models/tenant/payment.py
To'lovlar jadvali. Click va naqd to'lovlar.
click_transaction_id UNIQUE — duplikat to'lovdan himoya.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, DECIMAL, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id:                   Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:           Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    group_id:             Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=True)
    amount:               Mapped[float]               = mapped_column(DECIMAL(12, 2), nullable=False)
    currency:             Mapped[str]                 = mapped_column(String(5), default="UZS")
    payment_type:         Mapped[str]                 = mapped_column(String(30), default="subscription")   # subscription | debt_payment | advance
    payment_method:       Mapped[str]                 = mapped_column(String(30), default="cash")           # cash | click
    click_transaction_id: Mapped[Optional[str]]       = mapped_column(String(200), unique=True, nullable=True)
    click_paydoc_id:      Mapped[Optional[str]]       = mapped_column(String(200), nullable=True)
    status:               Mapped[str]                 = mapped_column(String(20), default="completed")      # pending | completed | failed | refunded
    received_by:          Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    period_month:         Mapped[Optional[int]]       = mapped_column(Integer, nullable=True)
    period_year:          Mapped[Optional[int]]       = mapped_column(Integer, nullable=True)
    note:                 Mapped[Optional[str]]       = mapped_column(Text, nullable=True)
    paid_at:              Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:           Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_payments_student", "student_id"),
        Index("idx_payments_status", "status"),
        Index("idx_payments_period", "period_year", "period_month"),
    )
