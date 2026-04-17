"""bot/utils/db.py — Bot uchun DB yordamchi funksiyalar."""
from typing import Optional, Tuple
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.public.tenant import Tenant


async def get_tenant_by_telegram_id(telegram_id: int) -> Optional[Tuple]:
    async with AsyncSessionLocal() as pub_session:
        tenants = (await pub_session.execute(
            select(Tenant).where(Tenant.is_active == True)
        )).scalars().all()

    for tenant in tenants:
        schema = tenant.schema_name
        async with AsyncSessionLocal() as session:
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            from app.models.tenant.user import User
            user = (await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()
            if user:
                return tenant, user
    return None


async def get_student_by_telegram_id(telegram_id: int) -> Optional[Tuple]:
    result = await get_tenant_by_telegram_id(telegram_id)
    if not result:
        return None
    tenant, user = result
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant.schema_name}", public'))
        from app.models.tenant.student import Student
        from app.models.tenant.gamification import GamificationProfile
        student = (await session.execute(
            select(Student).where(Student.user_id == user.id)
        )).scalar_one_or_none()
        if not student:
            return None
        gam = (await session.execute(
            select(GamificationProfile).where(GamificationProfile.student_id == student.id)
        )).scalar_one_or_none()
        return student, user, gam
