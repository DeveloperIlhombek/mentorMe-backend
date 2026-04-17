"""bot/handlers/admin.py — Admin buyruqlari"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.utils.db import get_tenant_by_telegram_id

router = Router(name="admin")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    tg_id  = message.from_user.id
    result = await get_tenant_by_telegram_id(tg_id)
    if not result:
        await message.answer("❌ Profil topilmadi.")
        return
    tenant, user = result

    if user.role not in ("admin", "super_admin"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    from sqlalchemy import select, text, func, and_
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.student import Student
    from app.models.tenant.group import Group
    from app.models.tenant.teacher import Teacher
    schema = tenant.schema_name

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        students = (await session.execute(select(func.count(Student.id)).where(Student.is_active == True))).scalar_one()
        groups   = (await session.execute(select(func.count(Group.id)).where(Group.status == "active"))).scalar_one()
        teachers = (await session.execute(select(func.count(Teacher.id)).where(Teacher.is_active == True))).scalar_one()
        debtors  = (await session.execute(select(func.count(Student.id)).where(and_(Student.balance < 0, Student.is_active == True)))).scalar_one()

    await message.answer(
        f"📊 <b>{tenant.name} — Statistika</b>\n\n"
        f"👤 O'quvchilar: <b>{students}</b>\n"
        f"👨‍🏫 O'qituvchilar: <b>{teachers}</b>\n"
        f"📚 Faol guruhlar: <b>{groups}</b>\n"
        f"⚠️ Qarzdorlar: <b>{debtors}</b>"
    )
