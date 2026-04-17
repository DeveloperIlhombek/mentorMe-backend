"""app/models/tenant/syllabus.py — O'quv yo'li modellari."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Syllabus(Base):
    __tablename__ = "syllabuses"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title       = Column(String(200), nullable=False)
    description = Column(Text)
    subject     = Column(String(100))
    created_by  = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    status      = Column(String(20), default="active")   # active | archived
    xp_per_topic= Column(Integer, default=50)
    color       = Column(String(7), default="#4f8ef7")
    icon        = Column(String(10), default="📚")
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at  = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SyllabusTopic(Base):
    __tablename__ = "syllabus_topics"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabuses.id", ondelete="CASCADE"), nullable=False)
    title       = Column(String(200), nullable=False)
    description = Column(Text)
    order_index = Column(Integer, nullable=False, default=0)
    xp_reward   = Column(Integer, default=50)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)


class SyllabusAssignment(Base):
    __tablename__ = "syllabus_assignments"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabuses.id", ondelete="CASCADE"), nullable=False)
    target_type = Column(String(20), nullable=False)   # group | student
    target_id   = Column(UUID(as_uuid=True), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class SyllabusProgress(Base):
    __tablename__ = "syllabus_progress"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id   = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    topic_id     = Column(UUID(as_uuid=True), ForeignKey("syllabus_topics.id", ondelete="CASCADE"), nullable=False)
    completed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    xp_given     = Column(Integer, default=0)