"""app/models/tenant/branch_ops.py — Filial xarajatlari va inspektor so'rovlari."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime,
    ForeignKey, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class BranchExpense(Base):
    """Filial xarajatlari — inspektor so'raydi, admin tasdiqlaydi."""
    __tablename__ = "branch_expenses"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id    = Column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))  # inspektor
    approved_by  = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))  # admin
    title        = Column(String(300), nullable=False)
    description  = Column(Text)
    amount       = Column(Numeric(15, 2), nullable=False)
    category     = Column(String(100))        # ijara, kommunal, jihozlar...
    status       = Column(String(20), nullable=False, default="pending")
    rejected_reason = Column(Text)
    approved_at  = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','paid')",
            name="ck_expense_status",
        ),
    )


class InspectorRequest(Base):
    """Inspektor → Admin: o'qituvchi qo'shish so'rovi."""
    __tablename__ = "inspector_requests"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id       = Column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    inspector_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    request_type    = Column(String(30), nullable=False, default="add_teacher")
    # Yangi o'qituvchi ma'lumotlari (JSON ichida)
    first_name      = Column(String(100), nullable=False)
    last_name       = Column(String(100))
    phone           = Column(String(20))
    subjects        = Column(String(500))    # vergul bilan ajratilgan
    salary_type     = Column(String(20))
    salary_amount   = Column(Numeric(12, 2))
    notes           = Column(Text)
    status          = Column(String(20), nullable=False, default="pending")
    reviewed_by     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reject_reason   = Column(Text)
    reviewed_at     = Column(DateTime(timezone=True))
    # Tasdiqlangandan so'ng yaratilgan teacher_id
    created_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_req_status",
        ),
        CheckConstraint(
            "request_type IN ('add_teacher','other')",
            name="ck_req_type",
        ),
    )
