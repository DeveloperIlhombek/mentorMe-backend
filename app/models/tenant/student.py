"""
app/models/tenant/student.py
Student va StudentGroup (ko'p-ko'p: talaba <-> guruh) modellari.
"""
import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import Boolean, Date, DateTime, DECIMAL, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Student(Base):
    __tablename__ = "students"

    id:            Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:       Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    branch_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    date_of_birth: Mapped[Optional[date]]      = mapped_column(Date, nullable=True)
    gender:        Mapped[Optional[str]]       = mapped_column(String(10), nullable=True)   # male | female
    parent_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    parent_phone:  Mapped[Optional[str]]       = mapped_column(String(20), nullable=True)
    balance:       Mapped[float]               = mapped_column(DECIMAL(12, 2), default=0)
    enrolled_at:   Mapped[date]                = mapped_column(Date, server_default=func.current_date())
    is_active:     Mapped[bool]                = mapped_column(Boolean, default=True)
    notes:          Mapped[Optional[str]]       = mapped_column(Text, nullable=True)
    payment_day:    Mapped[Optional[int]]       = mapped_column(SmallInteger, nullable=True, default=1)
    monthly_fee:    Mapped[Optional[float]]     = mapped_column(DECIMAL(12, 2), nullable=True)
    is_approved:        Mapped[bool]                = mapped_column(Boolean, default=True)
    is_rejected:        Mapped[bool]                = mapped_column(Boolean, default=False)
    pending_delete:     Mapped[bool]                = mapped_column(Boolean, default=False)
    # Teacher yaratganda guruh IDlar bu yerda saqlanadi (tasdiqlanganida StudentGroup ga ko'chiriladi)
    pending_group_ids:  Mapped[list]                = mapped_column(JSONB, default=list, server_default="'[]'::jsonb", nullable=False)
    created_by:         Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:         Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:         Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StudentGroup(Base):
    """Ko'p-ko'p: Student <-> Group orasidagi bog'lanish jadvali."""
    __tablename__ = "student_groups"

    id:         Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    group_id:   Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    joined_at:  Mapped[date]          = mapped_column(Date, server_default=func.current_date())
    left_at:    Mapped[Optional[date]]= mapped_column(Date, nullable=True)
    is_active:  Mapped[bool]          = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("student_id", "group_id", name="uq_student_group"),
    )
