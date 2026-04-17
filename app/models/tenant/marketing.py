"""app/models/tenant/marketing.py — Marketing modellari."""
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime,
    ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id                         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name                       = Column(String(200), nullable=False)
    description                = Column(Text)
    type                       = Column(String(30), nullable=False, default="referral")
    referrer_reward_type       = Column(String(30), default="bonus_sum")
    referrer_reward_value      = Column(Numeric(12, 2), default=0)
    new_student_discount_type  = Column(String(20), default="percent")
    new_student_discount_value = Column(Numeric(12, 2), default=0)
    max_uses                   = Column(Integer)
    used_count                 = Column(Integer, nullable=False, default=0)
    starts_at                  = Column(DateTime(timezone=True))
    ends_at                    = Column(DateTime(timezone=True))
    is_active                  = Column(Boolean, nullable=False, default=True)
    created_by                 = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at                 = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "type IN ('referral','invitation','seasonal','loyalty')",
            name="ck_campaign_type",
        ),
    )


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id   = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, unique=True)
    campaign_id  = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"))
    code         = Column(String(16), nullable=False, unique=True)
    total_uses   = Column(Integer, nullable=False, default=0)
    total_earned = Column(Numeric(12, 2), nullable=False, default=0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class ReferralUse(Base):
    __tablename__ = "referral_uses"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_id              = Column(UUID(as_uuid=True), ForeignKey("referral_codes.id", ondelete="CASCADE"), nullable=False)
    new_student_id       = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    referrer_bonus       = Column(Numeric(12, 2), nullable=False, default=0)
    new_student_discount = Column(Numeric(12, 2), nullable=False, default=0)
    status               = Column(String(20), nullable=False, default="pending")
    paid_at              = Column(DateTime(timezone=True))
    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("code_id", "new_student_id", name="uq_referral_use"),
        CheckConstraint("status IN ('pending','paid','cancelled')", name="ck_ref_status"),
    )


class Invitation(Base):
    __tablename__ = "invitations"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id     = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    campaign_id    = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"))
    code           = Column(String(32), nullable=False, unique=True)
    discount_type  = Column(String(20), nullable=False, default="percent")
    discount_value = Column(Numeric(12, 2), nullable=False, default=0)
    pdf_url        = Column(Text)
    qr_data        = Column(Text)
    used_by        = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"))
    used_at        = Column(DateTime(timezone=True))
    expires_at     = Column(DateTime(timezone=True))
    promo_text     = Column(Text)   # Admin jalb matni
    is_active      = Column(Boolean, nullable=False, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('percent','fixed','none')",
            name="ck_inv_discount",
        ),
    )


class Certificate(Base):
    __tablename__ = "certificates"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id       = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    certificate_type = Column(String(30), nullable=False, default="course")
    title            = Column(String(300), nullable=False)
    description      = Column(Text)
    issued_at        = Column(DateTime(timezone=True), server_default=func.now())
    issued_by        = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    pdf_url          = Column(Text)
    verify_code      = Column(String(32), nullable=False, unique=True)
    is_public        = Column(Boolean, nullable=False, default=True)
    metadata_        = Column("metadata", JSONB, nullable=False, server_default='{}')

    __table_args__ = (
        CheckConstraint(
            "certificate_type IN ('course','level','attendance','custom')",
            name="ck_cert_type",
        ),
    )


class ChurnRisk(Base):
    __tablename__ = "churn_risks"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id    = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, unique=True)
    risk_score    = Column(Numeric(5, 2), nullable=False, default=0)
    risk_level    = Column(String(20), nullable=False, default="low")
    signals       = Column(JSONB, nullable=False, server_default='[]')
    action_taken  = Column(String(200))
    resolved_at   = Column(DateTime(timezone=True))
    notified_at   = Column(DateTime(timezone=True))
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name="ck_churn_level",
        ),
    )
