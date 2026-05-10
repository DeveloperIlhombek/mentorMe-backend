"""
app/models/tenant/user_role.py

Bitta foydalanuvchi bir nechta rolda bo'lishi uchun many-to-many jadval.
Eski `users.role` ustuni "default/primary" rol sifatida saqlanadi
(login'dan keyin user qaysi rol bilan kirgani — JWT'ning `role` claim'i).
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id:    Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role:       Mapped[str]       = mapped_column(String(20), primary_key=True)
    branch_id:  Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active:  Mapped[bool]      = mapped_column(Boolean, default=True, nullable=False)
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    granted_at: Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_user_roles_role", "role"),
        Index("idx_user_roles_user_active", "user_id", "is_active"),
    )
