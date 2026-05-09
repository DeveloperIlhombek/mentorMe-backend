"""
app/models/tenant/notification.py
Bildirishnomalar: Telegram + in-app, dedupe, retry, preferences.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id:           Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:      Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type:         Mapped[str]                = mapped_column(String(50), nullable=False)
    category:     Mapped[str]                = mapped_column(String(30), nullable=False, default="system")
    priority:     Mapped[str]                = mapped_column(String(15), nullable=False, default="normal")
    title:        Mapped[str]                = mapped_column(String(200), nullable=False)
    body:         Mapped[str]                = mapped_column(Text, nullable=False)
    data:         Mapped[Optional[dict]]     = mapped_column(JSONB, default=dict)
    channel:      Mapped[str]                = mapped_column(String(20), default="telegram")
    status:       Mapped[str]                = mapped_column(String(15), nullable=False, default="queued")
    error:        Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    attempts:     Mapped[int]                = mapped_column(Integer, default=0)
    dedupe_key:   Mapped[Optional[str]]      = mapped_column(String(120), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read:      Mapped[bool]               = mapped_column(Boolean, default=False)
    sent_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:   Mapped[datetime]           = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "is_read", "created_at"),
        Index("idx_notifications_status_sched", "status", "scheduled_at"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
