"""
app/models/tenant/notification.py
Bildirishnomalar: Telegram xabarlar, in-app.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id:         Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:    Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type:       Mapped[str]                = mapped_column(String(50), nullable=False)        # payment_reminder | absence_alert | new_grade
    title:      Mapped[str]                = mapped_column(String(200), nullable=False)
    body:       Mapped[str]                = mapped_column(Text, nullable=False)
    data:       Mapped[Optional[dict]]     = mapped_column(JSONB, default=dict)
    channel:    Mapped[str]                = mapped_column(String(20), default="telegram")    # telegram | sms
    is_read:    Mapped[bool]               = mapped_column(Boolean, default=False)
    sent_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]           = mapped_column(DateTime(timezone=True), server_default=func.now())
