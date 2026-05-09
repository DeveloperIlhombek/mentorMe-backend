"""
app/models/public/telegram_link.py

Public schema'da deep-link token → (tenant_slug, user_id) mapping.
Bot /start <token> bilan kelganda barcha tenantlarni skan qilmaymiz.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"
    __table_args__ = {"schema": "public"}

    token        = Column(String(64), primary_key=True)
    tenant_slug  = Column(String(50), nullable=False)
    user_id      = Column(UUID(as_uuid=True), nullable=False)
    expires_at   = Column(DateTime(timezone=True), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
