"""
app/models/tenant/progress.py
O'quvchi o'zlashtirish darajasi (StudentProgress) modeli.
Har oy admin tomonidan belgilangan X va Y kunlarda o'qituvchi kiritadi.
"""
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class StudentProgress(Base):
    """
    O'quvchining o'zlashtirish darajasi (0–100%).
    Har oyda 2 marta (X va Y kunlarda) kiritiladi.
    O'quvchi va ota-onaga Telegram orqali yuboriladi.
    """
    __tablename__ = "student_progress"

    id:             Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:     Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    group_id:       Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    teacher_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)

    # Qaysi oy uchun
    period_month:   Mapped[int]                 = mapped_column(SmallInteger, nullable=False)
    period_year:    Mapped[int]                 = mapped_column(SmallInteger, nullable=False)

    # Rejalashtirilgan sana (masalan: 15-aprel yoki 28-aprel)
    scheduled_date: Mapped[date]                = mapped_column(Date, nullable=False)

    # O'qituvchi kiritgan qiymat (0.00 – 100.00)
    score:          Mapped[Optional[float]]     = mapped_column(Numeric(5, 2), nullable=True)

    # Holat: pending (kiritilmagan) | entered (kiritilgan) | missed (o'tkazib yuborilgan)
    status:         Mapped[str]                 = mapped_column(String(20), nullable=False, default="pending")

    # Izoh (masalan: "Dars mavzusini tushunmayapti")
    notes:          Mapped[Optional[str]]       = mapped_column(Text, nullable=True)

    # Telegram bildirish
    notified:       Mapped[bool]                = mapped_column(Boolean, default=False)
    notified_at:    Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True), nullable=True)

    # Vaqtida kiritilganmi
    is_late:        Mapped[bool]                = mapped_column(Boolean, default=False)

    # Qachon kiritilgan
    submitted_at:   Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:     Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:     Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Bir student uchun bir oyda bir scheduled_date — bir marta kiritiladi
        UniqueConstraint("student_id", "scheduled_date", name="uq_student_progress_date"),
        Index("idx_student_progress_student", "student_id"),
        Index("idx_student_progress_period", "period_year", "period_month"),
        Index("idx_student_progress_teacher", "teacher_id"),
    )
