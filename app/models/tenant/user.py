"""
app/models/tenant/user.py
Faqat User modeli shu yerda.
Barcha foydalanuvchilar: admin, teacher, student, parent.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id:                Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id:       Mapped[Optional[int]]    = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_username: Mapped[Optional[str]]    = mapped_column(String(100), nullable=True)
    email:             Mapped[Optional[str]]    = mapped_column(String(200), unique=True, nullable=True)
    password_hash:     Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    first_name:        Mapped[str]              = mapped_column(String(100), nullable=False)
    last_name:         Mapped[Optional[str]]    = mapped_column(String(100), nullable=True)
    phone:             Mapped[Optional[str]]    = mapped_column(String(20), unique=True, nullable=True)
    role:              Mapped[str]              = mapped_column(String(20), nullable=False)  # admin|teacher|student|parent|inspector
    branch_id:         Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    avatar_url:        Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    language_code:     Mapped[str]              = mapped_column(String(5), default="uz")
    is_active:         Mapped[bool]             = mapped_column(Boolean, default=True)
    is_verified:       Mapped[bool]             = mapped_column(Boolean, default=False)
    last_seen_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:        Mapped[datetime]         = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:        Mapped[datetime]         = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_users_telegram_id", "telegram_id"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
    )
