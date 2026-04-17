"""
app/services/__init__.py

Barcha service modullarini shu yerdan import qilish mumkin.

Ishlatish:
    from app.services import student, group, attendance, payment, gamification
    students, total = await student.get_students(db, page=1)
"""
from app.services import student
from app.services import group
from app.services import attendance
from app.services import payment
from app.services import gamification

__all__ = ["student", "group", "attendance", "payment", "gamification"]
