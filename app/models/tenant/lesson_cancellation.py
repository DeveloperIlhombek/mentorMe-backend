"""
app/models/tenant/lesson_cancellation.py
Dars bekor qilish va to'lov korreksiyasi modellari.

LessonCancellation — dars bekor qilinganda yoziladi (guruh yoki bitta o'quvchi).
PaymentAdjustment   — to'lov sanasi yoki miqdori o'zgarganda yoziladi.
"""
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, DECIMAL, ForeignKey, Numeric, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class LessonCancellation(Base):
    """
    Dars bekor qilish yozuvi.
    scope = 'group'   → guruhning barcha o'quvchilari ta'sirlanadi.
    scope = 'student' → faqat tanlangan o'quvchi ta'sirlanadi.
    """
    __tablename__ = "lesson_cancellations"

    id:             Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id:       Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    # scope = 'group' | 'student'
    scope:          Mapped[str]                 = mapped_column(String(20), nullable=False, default="group")
    # Faqat scope='student' bo'lganda to'ldiriladi
    student_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=True)

    # Bekor qilingan darsning sanasi
    lesson_date:    Mapped[date]                = mapped_column(Date, nullable=False)

    # Sabab
    reason:         Mapped[Optional[str]]       = mapped_column(Text, nullable=True)

    # To'lov korreksiyasi amalga oshirilganmi
    payment_adjusted: Mapped[bool]              = mapped_column(Boolean, default=False)

    created_by:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:     Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_lesson_cancel_group", "group_id"),
        Index("idx_lesson_cancel_date", "lesson_date"),
    )


class PaymentAdjustment(Base):
    """
    To'lov korreksiyasi.
    adj_type = 'credit' → keyingi to'lov sanasi uzayadi (dars bekor = o'quvchi foydasiga).
    adj_type = 'debit'  → keyingi to'lov sanasi qisqaradi (qo'shimcha dars = o'quvchi qarzi).

    amount — bir darsning narxi (monthly_fee / lessons_in_month).
    days_adjusted — payment_day ga qo'shiladigan/chiqariladigan kunlar soni.
    """
    __tablename__ = "payment_adjustments"

    id:              Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:      Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    group_id:        Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    # Sabab yozuvi (LessonCancellation bilan bog'lanishi)
    cancellation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("lesson_cancellations.id", ondelete="SET NULL"), nullable=True)

    # credit | debit
    adj_type:        Mapped[str]                 = mapped_column(String(20), nullable=False)

    # Bir darsning qiymati (so'm)
    amount:          Mapped[float]               = mapped_column(DECIMAL(12, 2), nullable=False, default=0)

    # Keyingi to'lov sanasi necha kun siljidi
    days_adjusted:   Mapped[int]                 = mapped_column(Numeric(6, 2), nullable=False, default=0)

    # Izoh
    note:            Mapped[Optional[str]]       = mapped_column(Text, nullable=True)

    created_by:      Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:      Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_payment_adj_student", "student_id"),
        Index("idx_payment_adj_group", "group_id"),
    )
