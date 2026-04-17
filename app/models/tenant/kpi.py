"""app/models/tenant/kpi.py — KPI modellari."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime,
    ForeignKey, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class KpiMetric(Base):
    """Admin belgilaydigan metrika shabloni."""
    __tablename__ = "kpi_metrics"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug         = Column(String(80), nullable=False, unique=True)
    name         = Column(String(200), nullable=False)
    description  = Column(Text)
    metric_type  = Column(String(30), nullable=False, default="percentage")
    direction    = Column(String(20), nullable=False, default="higher_better")
    unit         = Column(String(20), default="%")
    is_active    = Column(Boolean, nullable=False, default=True)
    created_by   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "metric_type IN ('percentage','count','rating','sum','custom')",
            name="ck_kpi_metric_type",
        ),
        CheckConstraint(
            "direction IN ('higher_better','lower_better')",
            name="ck_kpi_direction",
        ),
    )


class KpiRule(Base):
    """Metrika uchun chegara + mukofot qoidasi."""
    __tablename__ = "kpi_rules"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id     = Column(UUID(as_uuid=True), ForeignKey("kpi_metrics.id", ondelete="CASCADE"), nullable=False)
    threshold_min = Column(Numeric(10, 2))
    threshold_max = Column(Numeric(10, 2))
    reward_type   = Column(String(30), nullable=False, default="none")
    reward_value  = Column(Numeric(12, 2), nullable=False, default=0)
    period        = Column(String(20), nullable=False, default="monthly")
    label         = Column(String(100))     # "A'lo daraja", "Jarima" kabi
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "reward_type IN ('bonus_pct','bonus_sum','penalty_pct','penalty_sum','none')",
            name="ck_kpi_reward_type",
        ),
        CheckConstraint(
            "period IN ('monthly','weekly')",
            name="ck_kpi_period",
        ),
    )


class KpiResult(Base):
    """Oylik hisoblangan natija (Celery yozadi)."""
    __tablename__ = "kpi_results"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id     = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    metric_id      = Column(UUID(as_uuid=True), ForeignKey("kpi_metrics.id", ondelete="CASCADE"), nullable=False)
    period_month   = Column(SmallInteger, nullable=False)
    period_year    = Column(SmallInteger, nullable=False)
    actual_value   = Column(Numeric(10, 2))
    rule_id        = Column(UUID(as_uuid=True), ForeignKey("kpi_rules.id", ondelete="SET NULL"))
    reward_amount  = Column(Numeric(12, 2), nullable=False, default=0)
    notes          = Column(Text)
    calculated_at  = Column(DateTime(timezone=True), server_default=func.now())
    status         = Column(String(20), nullable=False, default="pending")

    __table_args__ = (
        UniqueConstraint("teacher_id", "metric_id", "period_month", "period_year",
                         name="uq_kpi_result"),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_kpi_month"),
        CheckConstraint("status IN ('pending','approved','paid')", name="ck_kpi_status"),
    )


class KpiPayslip(Base):
    """Oylik maosh slip — KPI natijalari yig'indisi."""
    __tablename__ = "kpi_payslips"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id    = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    period_month  = Column(SmallInteger, nullable=False)
    period_year   = Column(SmallInteger, nullable=False)
    base_salary   = Column(Numeric(15, 2), nullable=False, default=0)
    total_bonus   = Column(Numeric(15, 2), nullable=False, default=0)
    total_penalty = Column(Numeric(15, 2), nullable=False, default=0)
    net_salary    = Column(Numeric(15, 2), nullable=False, default=0)
    status        = Column(String(20), nullable=False, default="draft")
    approved_by   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at   = Column(DateTime(timezone=True))
    pdf_url       = Column(Text)
    notes         = Column(Text)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("teacher_id", "period_month", "period_year",
                         name="uq_kpi_payslip"),
        CheckConstraint("status IN ('draft','approved','paid')", name="ck_payslip_status"),
    )
