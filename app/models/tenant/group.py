"""
app/models/tenant/group.py
Guruh modeli. schedule JSONB: [{day, start, end, room}]
"""
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, DECIMAL, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Group(Base):
    __tablename__ = "groups"

    id:          Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:        Mapped[str]                 = mapped_column(String(200), nullable=False)
    branch_id:   Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    teacher_id:  Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)
    subject:     Mapped[str]                 = mapped_column(String(200), nullable=False)
    level:       Mapped[Optional[str]]       = mapped_column(String(50), nullable=True)
    schedule:    Mapped[Optional[dict]]      = mapped_column(JSONB, nullable=True)
    start_date:  Mapped[Optional[date]]      = mapped_column(Date, nullable=True)
    end_date:    Mapped[Optional[date]]      = mapped_column(Date, nullable=True)
    monthly_fee: Mapped[Optional[float]]     = mapped_column(DECIMAL(12, 2), nullable=True)
    max_students:Mapped[int]                 = mapped_column(Integer, default=15)
    status:      Mapped[str]                 = mapped_column(String(20), default="active")  # active | completed | paused
    created_at:  Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # O'qituvchi baholashni topshirishi kerak bo'lgan kun va soat (oylik)
    progress_deadline_day:  Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    progress_deadline_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=23)
