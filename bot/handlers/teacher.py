"""bot/handlers/teacher.py — O'qituvchi buyruqlari"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.utils.db import get_tenant_by_telegram_id

router = Router(name="teacher")


@router.message(Command("mygroups"))
async def cmd_my_groups(message: Message):
    tg_id  = message.from_user.id
    result = await get_tenant_by_telegram_id(tg_id)
    if not result:
        await message.answer("❌ Profil topilmadi.")
        return
    tenant, user = result

    from sqlalchemy import select, text, and_
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.teacher import Teacher
    from app.models.tenant.group import Group
    schema = tenant.schema_name
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        teacher = (await session.execute(select(Teacher).where(Teacher.user_id == user.id))).scalar_one_or_none()
        if not teacher:
            await message.answer("❌ O'qituvchi profili topilmadi.")
            return
        groups = (await session.execute(
            select(Group).where(and_(Group.teacher_id == teacher.id, Group.status == "active"))
        )).scalars().all()

    if not groups:
        await message.answer("📚 Aktiv guruhlar yo'q.")
        return

    from datetime import date
    today_wd = date.today().isoweekday()
    DAY = ["","Du","Se","Ch","Pa","Ju","Sh","Ya"]

    lines = ["📚 <b>Guruhlaringiz:</b>\n"]
    for g in groups:
        schedule_today = ""
        if g.schedule:
            for slot in g.schedule:
                if slot.get("day") == today_wd:
                    schedule_today = f" — bugun {slot['start']}"
        lines.append(f"• <b>{g.name}</b>{schedule_today}")

    await message.answer("\n".join(lines))


@router.message(Command("today"))
async def cmd_today(message: Message):
    """Bugungi jadval."""
    tg_id  = message.from_user.id
    result = await get_tenant_by_telegram_id(tg_id)
    if not result:
        await message.answer("❌ Profil topilmadi.")
        return
    tenant, user = result

    from sqlalchemy import select, text, and_
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.teacher import Teacher
    from app.models.tenant.group import Group
    from datetime import date
    today_wd = date.today().isoweekday()
    DAY_NAMES = ["","Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]

    schema = tenant.schema_name
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        teacher = (await session.execute(select(Teacher).where(Teacher.user_id == user.id))).scalar_one_or_none()
        if not teacher:
            await message.answer("❌ O'qituvchi profili topilmadi.")
            return
        groups = (await session.execute(
            select(Group).where(and_(Group.teacher_id == teacher.id, Group.status == "active"))
        )).scalars().all()

    today_lessons = []
    for g in groups:
        if g.schedule:
            for slot in g.schedule:
                if slot.get("day") == today_wd:
                    today_lessons.append((slot.get("start",""), g.name, slot.get("room","")))

    today_lessons.sort(key=lambda x: x[0])

    if not today_lessons:
        await message.answer(f"📅 Bugun ({DAY_NAMES[today_wd]}) dars yo'q.")
        return

    lines = [f"📅 <b>Bugun ({DAY_NAMES[today_wd]}):</b>\n"]
    for start, name, room in today_lessons:
        lines.append(f"🕐 {start} — <b>{name}</b>" + (f" (xona {room})" if room else ""))
    await message.answer("\n".join(lines))
