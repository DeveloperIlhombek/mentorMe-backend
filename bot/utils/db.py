"""
bot/utils/db.py — Bot uchun DB yordamchi funksiyalar.

Multi-tenant arxitektura:
  - public schema: Tenant jadvali (tenant_slug → schema_name)
  - tenant schema: User, Student, Teacher, Parent modellari

Barcha funksiyalar telegram_id bo'yicha tenant + user topadi.
"""
import uuid
from typing import Optional, Tuple

from sqlalchemy import select, text, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.public.tenant import Tenant


# ── Tenant + User topish ─────────────────────────────────────────────────

async def get_tenant_and_user(telegram_id: int) -> Optional[Tuple[Tenant, object]]:
    """
    Telegram ID bo'yicha barcha tenantlarda User qidiradi.
    Qaytaradi: (Tenant, User) yoki None.
    """
    from app.models.tenant.user import User

    async with AsyncSessionLocal() as pub:
        tenants = (await pub.execute(
            select(Tenant).where(Tenant.is_active == True)
        )).scalars().all()

    for tenant in tenants:
        schema = tenant.schema_name
        async with AsyncSessionLocal() as session:
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            user = (await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()
            if user:
                return tenant, user
    return None


# ── Legacy alias ─────────────────────────────────────────────────────────
async def get_tenant_by_telegram_id(telegram_id: int) -> Optional[Tuple]:
    return await get_tenant_and_user(telegram_id)


# ── Student ──────────────────────────────────────────────────────────────

async def get_student_by_telegram_id(telegram_id: int) -> Optional[Tuple]:
    """
    Qaytaradi: (Student, User, GamificationProfile | None) yoki None.
    """
    from app.models.tenant.student import Student
    from app.models.tenant.gamification import GamificationProfile

    result = await get_tenant_and_user(telegram_id)
    if not result:
        return None
    tenant, user = result
    schema = tenant.schema_name

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        student = (await session.execute(
            select(Student).where(Student.user_id == user.id)
        )).scalar_one_or_none()
        if not student:
            return None
        gam = (await session.execute(
            select(GamificationProfile).where(GamificationProfile.student_id == student.id)
        )).scalar_one_or_none()
        return student, user, gam


async def get_student_attendance_summary(
    tenant_schema: str,
    student_id: uuid.UUID,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> dict:
    """
    O'quvchi davomat statistikasini hisoblash.
    """
    from app.models.tenant.attendance import Attendance
    from datetime import date

    now = date.today()
    m = month or now.month
    y = year or now.year

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))

        # Oylik davomat
        from sqlalchemy import extract
        stmt = select(Attendance).where(
            and_(
                Attendance.student_id == student_id,
                extract("month", Attendance.date) == m,
                extract("year",  Attendance.date) == y,
            )
        )
        records = (await session.execute(stmt)).scalars().all()

    present  = sum(1 for r in records if r.status == "present")
    absent   = sum(1 for r in records if r.status == "absent")
    late     = sum(1 for r in records if r.status == "late")
    excused  = sum(1 for r in records if r.status == "excused")
    total    = len(records)
    percent  = round((present + late * 0.5) / total * 100) if total > 0 else 0

    return {
        "present": present,
        "absent":  absent,
        "late":    late,
        "excused": excused,
        "total":   total,
        "percent": percent,
    }


# ── Teacher ──────────────────────────────────────────────────────────────

async def get_teacher_by_telegram_id(telegram_id: int) -> Optional[Tuple]:
    """Qaytaradi: (Teacher, User, Tenant) yoki None."""
    from app.models.tenant.teacher import Teacher

    result = await get_tenant_and_user(telegram_id)
    if not result:
        return None
    tenant, user = result
    schema = tenant.schema_name

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        teacher = (await session.execute(
            select(Teacher).where(Teacher.user_id == user.id)
        )).scalar_one_or_none()
        if not teacher:
            return None
        return teacher, user, tenant


# ── Parent ───────────────────────────────────────────────────────────────

async def get_parent_children(tenant_schema: str, parent_user_id: uuid.UUID) -> list:
    """Ota-onaning farzandlari."""
    from app.models.tenant.student import Student
    from app.models.tenant.user import User

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        stmt = (
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .where(Student.parent_id == parent_user_id)
        )
        rows = (await session.execute(stmt)).all()
    return rows


# ── Admin ────────────────────────────────────────────────────────────────

async def get_tenant_stats(tenant_schema: str) -> dict:
    """Tenant umumiy statistikasi."""
    from app.models.tenant.student import Student
    from app.models.tenant.teacher import Teacher
    from app.models.tenant.group import Group

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        students = (await session.execute(
            select(func.count(Student.id)).where(Student.is_active == True)
        )).scalar_one()
        teachers = (await session.execute(
            select(func.count(Teacher.id)).where(Teacher.is_active == True)
        )).scalar_one()
        groups = (await session.execute(
            select(func.count(Group.id)).where(Group.status == "active")
        )).scalar_one()
        debtors = (await session.execute(
            select(func.count(Student.id)).where(
                and_(Student.balance < 0, Student.is_active == True)
            )
        )).scalar_one()
        pending = (await session.execute(
            select(func.count(Student.id)).where(
                and_(Student.is_approved == False, Student.is_active == False)
            )
        )).scalar_one()

    return {
        "students": students,
        "teachers": teachers,
        "groups":   groups,
        "debtors":  debtors,
        "pending":  pending,
    }
