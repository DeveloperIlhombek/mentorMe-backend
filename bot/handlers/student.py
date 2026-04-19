"""
bot/handlers/student.py

O'quvchi uchun bot buyruqlari:
  /profile    — profil + XP + daraja
  /attendance — oylik davomat
  /balance    — balans
  /streak     — streak
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.utils.db import get_student_by_telegram_id, get_student_attendance_summary
from bot.utils.keyboards import back_keyboard
from datetime import date

router = Router(name="student")

XP_LEVELS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500]
XP_NAMES  = ["Yangi boshlovchi","Izlanuvchi","O'rganuvchi","Amaliyotchi",
              "Mutaxassis","Ekspert","Usta","Meister","Champion","Legenda"]


def _level(xp: int) -> tuple[int, str]:
    level = 1
    for i, t in enumerate(XP_LEVELS):
        if xp >= t:
            level = i + 1
    level = min(level, 10)
    return level, XP_NAMES[level - 1]


def _progress_bar(xp: int) -> str:
    for i in range(len(XP_LEVELS) - 1):
        if xp < XP_LEVELS[i + 1]:
            current_lvl_xp = XP_LEVELS[i]
            next_lvl_xp    = XP_LEVELS[i + 1]
            pct = (xp - current_lvl_xp) / (next_lvl_xp - current_lvl_xp)
            filled  = int(pct * 10)
            bar     = "█" * filled + "░" * (10 - filled)
            left    = next_lvl_xp - xp
            return f"[{bar}] {int(pct*100)}% ({left} XP qoldi)"
    return "[██████████] MAX"


# ── Shared text helpers (used by start.py callbacks) ─────────────────────

async def _get_profile_text(tg_id: int) -> str:
    data = await get_student_by_telegram_id(tg_id)
    if not data:
        return "❌ Siz ro'yxatdan o'tmagansiz.\nAdmin bilan bog'laning."
    student, user, gam = data
    xp      = gam.total_xp       if gam else 0
    streak  = gam.current_streak if gam else 0
    weekly  = gam.weekly_xp      if gam else 0
    level, lvl_name = _level(xp)
    bar = _progress_bar(xp)
    balance = float(student.balance)
    bal_str = f"✅ +{balance:,.0f} so'm" if balance >= 0 else f"⚠️ Qarz: {abs(balance):,.0f} so'm"
    return (
        f"👤 <b>{user.first_name} {user.last_name or ''}</b>\n"
        f"📱 {user.phone or '—'}  |  📧 {user.email or '—'}\n\n"
        f"⭐ Daraja: <b>{level} — {lvl_name}</b>\n"
        f"📊 {bar}\n"
        f"🏆 Jami XP: <b>{xp:,}</b>  |  Bu hafta: <b>{weekly:,}</b>\n"
        f"🔥 Streak: <b>{streak} kun</b>\n\n"
        f"💰 Balans: <b>{bal_str}</b>"
    )


async def _get_attendance_text(tg_id: int) -> str:
    from bot.utils.db import get_tenant_and_user
    from app.models.tenant.student import Student
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal

    result = await get_tenant_and_user(tg_id)
    if not result:
        return "❌ Profil topilmadi."
    tenant, user = result
    schema = tenant.schema_name

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        student = (await session.execute(
            select(Student).where(Student.user_id == user.id)
        )).scalar_one_or_none()
        if not student:
            return "❌ O'quvchi profili topilmadi."
        student_id = student.id

    now = date.today()
    MONTHS = ["","Yanvar","Fevral","Mart","Aprel","May","Iyun",
               "Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"]
    att = await get_student_attendance_summary(schema, student_id, now.month, now.year)

    bar_filled = int(att["percent"] / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    color = "🟢" if att["percent"] >= 80 else "🟡" if att["percent"] >= 60 else "🔴"

    return (
        f"📅 <b>Davomat — {MONTHS[now.month]} {now.year}</b>\n\n"
        f"✅ Keldi:    <b>{att['present']}</b>\n"
        f"❌ Kelmadi:  <b>{att['absent']}</b>\n"
        f"⏰ Kechikdi: <b>{att['late']}</b>\n"
        f"📝 Uzrli:    <b>{att['excused']}</b>\n\n"
        f"{color} [{bar}] <b>{att['percent']}%</b>"
    )


# ── Message handlers ───────────────────────────────────────────────────────

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    text = await _get_profile_text(message.from_user.id)
    await message.answer(text, reply_markup=back_keyboard())


@router.message(Command("attendance"))
async def cmd_attendance(message: Message):
    text = await _get_attendance_text(message.from_user.id)
    await message.answer(text, reply_markup=back_keyboard())


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    data = await get_student_by_telegram_id(message.from_user.id)
    if not data:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")
        return
    student, _, _ = data
    balance = float(student.balance)
    if balance > 0:
        text = f"💰 Balansingiz: <b>+{balance:,.0f} so'm</b>\n✅ Ortiqcha to'lov mavjud"
    elif balance < 0:
        text = (
            f"⚠️ Qarzingiz: <b>{abs(balance):,.0f} so'm</b>\n"
            f"Iltimos, imkon qadar to'lovni amalga oshiring."
        )
    else:
        text = "💰 Balansingiz: <b>0 so'm</b> — to'lov muddatida."
    await message.answer(text, reply_markup=back_keyboard())


@router.message(Command("streak"))
async def cmd_streak(message: Message):
    data = await get_student_by_telegram_id(message.from_user.id)
    if not data:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")
        return
    _, _, gam = data
    streak     = gam.current_streak if gam else 0
    max_streak = gam.max_streak     if gam else 0
    weekly     = gam.weekly_xp      if gam else 0

    if streak >= 30: emoji = "💎"
    elif streak >= 14: emoji = "🔥"
    elif streak >= 7: emoji = "⚡"
    elif streak >= 3: emoji = "📈"
    else: emoji = "📅"

    text = f"{emoji} <b>Streak: {streak} kun</b>\n\n"
    text += f"🏆 Shaxsiy rekord: <b>{max_streak} kun</b>\n"
    text += f"📈 Bu hafta: <b>{weekly:,} XP</b>\n\n"

    if streak == 0:
        text += "Bugun darsga keling va streakni boshlang! 🚀"
    elif streak < 7:
        text += f"Davom eting! {7 - streak} kundan keyin 🔥 bonus!"
    elif streak < 30:
        text += f"Ajoyib! {30 - streak} kun qoldi 💎 rekordga!"
    else:
        text += "Siz champion! Streakni saqlang! 💎"

    await message.answer(text, reply_markup=back_keyboard())
