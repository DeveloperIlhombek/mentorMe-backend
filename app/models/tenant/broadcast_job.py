"""
app/models/tenant/broadcast_job.py

Admin paneldan yuborilgan broadcast (e'lon) progress kuzatuvi.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id:           Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by:   Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title:        Mapped[str]                = mapped_column(String(200), nullable=False)
    body:         Mapped[str]                = mapped_column(Text, nullable=False)
    data:         Mapped[Optional[dict]]     = mapped_column(JSONB, default=dict)
    filters:      Mapped[Optional[dict]]     = mapped_column(JSONB, default=dict)  # {role:[...], branch_id, group_id}
    channels:     Mapped[Optional[list]]     = mapped_column(JSONB, default=lambda: ["telegram", "in_app"])
    total:        Mapped[int]                = mapped_column(Integer, default=0)
    sent:         Mapped[int]                = mapped_column(Integer, default=0)
    failed:       Mapped[int]                = mapped_column(Integer, default=0)
    status:       Mapped[str]                = mapped_column(String(15), default="queued")  # queued|running|done|cancelled
    created_at:   Mapped[datetime]           = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
