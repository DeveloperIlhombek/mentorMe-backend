"""
app/models/tenant/branch.py
Filiallar modeli.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Branch(Base):
    __tablename__ = "branches"

    id:         Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:       Mapped[str]                 = mapped_column(String(200), nullable=False)
    address:    Mapped[Optional[str]]       = mapped_column(Text, nullable=True)
    phone:      Mapped[Optional[str]]       = mapped_column(String(20), nullable=True)
    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_main:    Mapped[bool]                = mapped_column(Boolean, default=False)
    is_active:  Mapped[bool]                = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())
