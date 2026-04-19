"""
bot/handlers/teacher.py — O'qituvchi buyruqlari
  /mygroups — Guruhlarim
  /today    — Bugungi darslar
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.utils.db import get_teacher_by_telegram_id
from bot.utils.keyboards import back_keyboard
from datetime import date

router = Router(name="teacher")

DAY_NAMES = ["","Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]


async def _get_groups_text(tg_id: int) -> str:
    data = await get_teacher_by_telegram_id(tg_id)
    if not data:
        return "❌ O'qituvchi profili topilmadi."
    teacher, user, tenant = data
    schema = tenant.schema_name

    from sqlalchemy import select, text, and_
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.group import Group

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        groups = (await session.execute(
            select(Group).where(and_(Group.teacher_id == teacher.id, Group.status == "active"))
        )).scalars().all()

    if not groups:
        return "📚 Faol guruhlar yo'q."

    today_wd = date.today().isoweekday()
    lines = [f"📚 <b>Guruhlarim ({len(groups)} ta):</b>\n"]
    for g in groups:
        today_slot = ""
        if g.schedule:
            for slot in (g.schedule if isinstance(g.schedule, list) else []):
                if slot.get("day") == today_wd:
                    today_slot = f" — bugun {slot.get('start','')}"
        students_info = f"👥 {g.max_students or '?'} o'rin"
        lines.append(f"• <b>{g.name}</b>{today_slot}\n  📖 {g.subject}  {students_info}")

    return "\n".join(lines)


async def _get_today_text(tg_id: int) -> str:
    data = await get_teacher_by_telegram_id(tg_id)
    if not data:
        return "❌ O'qituvchi profili topilmadi."
    teacher, user, tenant = data
    schema = tenant.schema_name

    from sqlalchemy import select, text, and_
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.group import Group

    today_wd = date.today().isoweekday()

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        groups = (await session.execute(
            select(Group).where(and_(Group.teacher_id == teacher.id, Group.status == "active"))
        )).scalars().all()

    today_lessons = []
    for g in groups:
        if g.schedule:
            for slot in (g.schedule if isinstance(g.schedule, list) else []):
                if slot.get("day") == today_wd:
                    today_lessons.append({
                        "start": slot.get("start", ""),
                        "end":   slot.get("end", ""),
                        "room":  slot.get("room", ""),
                        "name":  g.name,
                        "subj":  g.subject,
                    })

    today_lessons.sort(key=lambda x: x["start"])

    if not today_lessons:
        return f"📅 Bugun ({DAY_NAMES[today_wd]}) dars yo'q. Yaxshi dam oling! 😊"

    lines = [f"📅 <b>Bugun — {DAY_NAMES[today_wd]}:</b>\n"]
    for ls in today_lessons:
        room = f" | 🚪 Xona {ls['room']}" if ls["room"] else ""
        end  = f"–{ls['end']}" if ls["end"] else ""
        lines.append(f"🕐 {ls['start']}{end} — <b>{ls['name']}</b>{room}")

    return "\n".join(lines)


@router.message(Command("mygroups"))
async def cmd_my_groups(message: Message):
    text = await _get_groups_text(message.from_user.id)
    await message.answer(text, reply_markup=back_keyboard())


@router.message(Command("today"))
async def cmd_today(message: Message):
    text = await _get_today_text(message.from_user.id)
    await message.answer(text, reply_markup=back_keyboard())
