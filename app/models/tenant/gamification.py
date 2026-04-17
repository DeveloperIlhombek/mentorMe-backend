"""
app/models/tenant/gamification.py
XP tizimi: GamificationProfile, XpTransaction, Achievement, StudentAchievement.
"""
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class GamificationProfile(Base):
    """Har bir o'quvchi uchun bitta profil."""
    __tablename__ = "gamification_profiles"

    id:                 Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:         Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey("students.id"), unique=True, nullable=False)
    total_xp:           Mapped[int]           = mapped_column(Integer, default=0)
    current_level:      Mapped[int]           = mapped_column(Integer, default=1)
    current_streak:     Mapped[int]           = mapped_column(Integer, default=0)
    max_streak:         Mapped[int]           = mapped_column(Integer, default=0)
    last_activity_date: Mapped[Optional[date]]= mapped_column(Date, nullable=True)
    weekly_xp:          Mapped[int]           = mapped_column(Integer, default=0)
    weekly_reset_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_gamification_weekly_xp", "weekly_xp"),
    )


class XpTransaction(Base):
    """Har bir XP berish/olish yozuvi."""
    __tablename__ = "xp_transactions"

    id:           Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:   Mapped[uuid.UUID]           = mapped_column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    amount:       Mapped[int]                 = mapped_column(Integer, nullable=False)             # Musbat yoki manfiy
    reason:       Mapped[str]                 = mapped_column(String(100), nullable=False)         # lesson_attended | test_passed | streak_bonus
    reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # attendance_id yoki progress_id
    created_at:   Mapped[datetime]            = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_xp_transactions_student", "student_id"),
    )


class Achievement(Base):
    """Yutuqlar shabloni (barcha o'quvchilar uchun umumiy)."""
    __tablename__ = "achievements"

    id:             Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug:           Mapped[str]           = mapped_column(String(50), unique=True, nullable=False)  # streak_7 | xp_1000
    name_uz:        Mapped[str]           = mapped_column(String(100), nullable=False)
    name_ru:        Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description_uz: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon:           Mapped[Optional[str]] = mapped_column(String(10), nullable=True)               # Emoji
    xp_reward:      Mapped[int]           = mapped_column(Integer, default=0)
    condition_type: Mapped[str]           = mapped_column(String(50), nullable=False)              # streak | xp | tests_passed | attendance
    condition_value:Mapped[int]           = mapped_column(Integer, nullable=False)
    is_active:      Mapped[bool]          = mapped_column(Boolean, default=True)


class StudentAchievement(Base):
    """O'quvchi qaysi yutuqni qachon olganini saqlaydi."""
    __tablename__ = "student_achievements"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    achievement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("achievements.id"), nullable=False)
    earned_at:      Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "achievement_id", name="uq_student_achievement"),
    )
