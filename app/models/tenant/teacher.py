"""
app/models/tenant/teacher.py
O'qituvchi modeli. users jadvalidan user_id orqali bog'langan.
"""
import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import Boolean, Date, DateTime, DECIMAL, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id:            Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:       Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    branch_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    subjects:      Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    bio:           Mapped[Optional[str]]       = mapped_column(Text, nullable=True)
    salary_type:   Mapped[Optional[str]]       = mapped_column(String(20), nullable=True)   # fixed | percent | per_lesson
    salary_amount: Mapped[Optional[float]]     = mapped_column(DECIMAL(12, 2), nullable=True)
    hired_at:      Mapped[Optional[date]]      = mapped_column(Date, nullable=True)
    kpi_calc_day:  Mapped[Optional[int]]       = mapped_column(SmallInteger, nullable=True)  # 1-31: KPI oylik hisoblash kuni
    is_active:        Mapped[bool]                = mapped_column(Boolean, default=True)
    is_approved:      Mapped[bool]                = mapped_column(Boolean, default=False)
    created_by:       Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_role:  Mapped[Optional[str]]       = mapped_column(String(20), nullable=True)   # admin | instructor | teacher
    created_at:       Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:       Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
