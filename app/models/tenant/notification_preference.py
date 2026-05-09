"""
app/models/tenant/notification_preference.py

Foydalanuvchi notification preferences: per-category opt-out, quiet hours.
Critical priority bo'lsa preferences override qilinadi.
"""
import uuid
from datetime import datetime, time
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Time
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id:                  Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:             Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    telegram_enabled:    Mapped[bool]           = mapped_column(Boolean, default=True)
    in_app_enabled:      Mapped[bool]           = mapped_column(Boolean, default=True)
    disabled_categories: Mapped[list[str]]      = mapped_column(ARRAY(String(30)), default=list)
    quiet_hours_start:   Mapped[Optional[time]] = mapped_column(Time, nullable=True, default=time(22, 0))
    quiet_hours_end:     Mapped[Optional[time]] = mapped_column(Time, nullable=True, default=time(7, 0))
    timezone:            Mapped[str]            = mapped_column(String(40), default="Asia/Tashkent")
    created_at:          Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:          Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
