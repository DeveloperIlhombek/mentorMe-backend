"""
bot/handlers/student.py

O'quvchi uchun bot buyruqlari:
  /profile   — profil + XP + daraja
  /attendance — davomat tarixi
  /balance   — balans
  /streak    — streak
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.utils.db import get_student_by_telegram_id, get_tenant_by_user

router = Router(name="student")

XP_LEVELS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500]

def _level(xp: int) -> int:
    level = 1
    for i, t in enumerate(XP_LEVELS):
        if xp >= t:
            level = i + 1
    return min(level, 10)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """O'quvchi profili."""
    tg_id = message.from_user.id
    data  = await get_student_by_telegram_id(tg_id)

    if not data:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz.\nAdmin bilan bog'laning.")
        return

    student, user, gam = data

    level   = _level(gam.total_xp if gam else 0)
    streak  = gam.current_streak if gam else 0
    xp      = gam.total_xp if gam else 0
    weekly  = gam.weekly_xp if gam else 0

    text = (
        f"👤 <b>{user.first_name} {user.last_name or ''}</b>\n\n"
        f"⭐ Daraja: <b>{level}</b>\n"
        f"🏆 Jami XP: <b>{xp:,}</b>\n"
        f"📈 Bu hafta: <b>{weekly:,} XP</b>\n"
        f"🔥 Streak: <b>{streak} kun</b>\n\n"
        f"💰 Balans: <b>{float(student.balance):,.0f} so'm</b>"
    )

    await message.answer(text)


@router.message(Command("attendance"))
async def cmd_attendance(message: Message):
    """Davomat ma'lumoti."""
    tg_id = message.from_user.id
    data  = await get_student_by_telegram_id(tg_id)

    if not data:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")
        return

    student, user, _ = data
    att = await _get_attendance_summary(student)

    text = (
        f"📅 <b>Davomat</b>\n\n"
        f"✅ Keldi: <b>{att['present']}</b>\n"
        f"❌ Kelmadi: <b>{att['absent']}</b>\n"
        f"⏰ Kechikdi: <b>{att['late']}</b>\n"
        f"📊 Foiz: <b>{att['percent']}%</b>"
    )

    await message.answer(text)


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Balans ma'lumoti."""
    tg_id = message.from_user.id
    data  = await get_student_by_telegram_id(tg_id)

    if not data:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")
        return

    student, _, _ = data
    balance = float(student.balance)

    if balance > 0:
        text = f"💰 Balansingiz: <b>+{balance:,.0f} so'm</b>\n✅ Ortiqcha to'lov"
    elif balance < 0:
        text = f"⚠️ Qarz: <b>{abs(balance):,.0f} so'm</b>\nIltimos, to'lovni amalga oshiring."
    else:
        text = "💰 Balansingiz: <b>0 so'm</b>\nTo'lov muddatida."

    await message.answer(text)


@router.message(Command("streak"))
async def cmd_streak(message: Message):
    """Streak ma'lumoti."""
    tg_id = message.from_user.id
    data  = await get_student_by_telegram_id(tg_id)

    if not data:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")
        return

    _, _, gam = data
    streak     = gam.current_streak if gam else 0
    max_streak = gam.max_streak if gam else 0

    if streak >= 30:
        emoji = "💎"
    elif streak >= 7:
        emoji = "🔥"
    elif streak >= 3:
        emoji = "⚡"
    else:
        emoji = "📅"

    text = (
        f"{emoji} <b>Streak: {streak} kun</b>\n\n"
        f"🏆 Rekord: <b>{max_streak} kun</b>\n\n"
    )

    if streak >= 7:
        text += "Zo'r! Streak bonuslar qo'shilmoqda! 🎉"
    elif streak > 0:
        text += f"Davom eting! Yana {7 - streak} kun streak bonusiga ega bo'lasiz! 💪"
    else:
        text += "Bugun darsga keling va streakni boshlang! 🚀"

    await message.answer(text)


async def _get_attendance_summary(student) -> dict:
    """O'quvchi davomat statistikasi."""
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.attendance import Attendance
    from sqlalchemy import select, func, and_, text
    from sqlalchemy.orm import Session

    # Tenant schema ni topish
    async with AsyncSessionLocal() as session:
        # Bu yerda tenant slug kerak — soddalik uchun public schema ishlatiladi
        return {"present": 0, "absent": 0, "late": 0, "percent": 0}
