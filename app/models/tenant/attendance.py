"""
app/models/tenant/attendance.py
Davomat jadvali. UNIQUE: (student_id, group_id, date)
"""
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Attendance(Base):
    __tablename__ = "attendance"

    id:              Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:      Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    group_id:        Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False)
    teacher_id:      Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)
    date:            Mapped[date]                = mapped_column(Date, nullable=False)
    status:          Mapped[str]                 = mapped_column(String(20), nullable=False)  # present | absent | late | excused
    arrived_at:      Mapped[Optional[str]]       = mapped_column(Time, nullable=True)
    note:            Mapped[Optional[str]]       = mapped_column(Text, nullable=True)
    parent_notified: Mapped[bool]                = mapped_column(Boolean, default=False)
    notified_at:     Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True), nullable=True)
    # O'qituvchi davomatni qachon kiritgani (kechikishni hisoblash uchun)
    submitted_at:    Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True), nullable=True)
    is_late_entry:   Mapped[bool]                = mapped_column(Boolean, default=False, nullable=False)
    created_at:      Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "group_id", "date", name="uq_attendance_student_group_date"),
        Index("idx_attendance_student_date", "student_id", "date"),
        Index("idx_attendance_group_date", "group_id", "date"),
    )
