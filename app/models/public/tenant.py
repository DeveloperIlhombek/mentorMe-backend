import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


def now_utc():
    return datetime.now(timezone.utc)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = {"schema": "public"}

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name            = Column(String(50), nullable=False)
    slug            = Column(String(30), unique=True, nullable=False)
    price_monthly   = Column(Integer, nullable=False)
    max_students    = Column(Integer, nullable=True)
    max_teachers    = Column(Integer, nullable=True)
    max_branches    = Column(Integer, default=1)
    features        = Column(JSONB, default=dict)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), default=now_utc)

    tenants = relationship("Tenant", back_populates="plan")


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "public"}

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug                = Column(String(50), unique=True, nullable=False)
    name                = Column(String(200), nullable=False)
    schema_name         = Column(String(60), unique=True, nullable=False)
    owner_telegram_id   = Column(BigInteger, nullable=True)
    phone               = Column(String(20), nullable=True)
    address             = Column(Text, nullable=True)
    logo_url            = Column(Text, nullable=True)
    plan_id             = Column(UUID(as_uuid=True), ForeignKey("public.subscription_plans.id"), nullable=True)
    subscription_status = Column(String(20), default="trial")
    trial_ends_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc) + timedelta(days=14))
    click_merchant_id   = Column(String(100), nullable=True)
    click_service_id    = Column(String(100), nullable=True)
    bot_token           = Column(Text, nullable=True)
    bot_username        = Column(String(100), nullable=True)
    custom_domain       = Column(String(200), nullable=True)
    brand_color         = Column(String(7), default="#3B82F6")
    is_active           = Column(Boolean, default=True)
    created_at          = Column(DateTime(timezone=True), default=now_utc)
    updated_at          = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    plan = relationship("SubscriptionPlan", back_populates="tenants")
