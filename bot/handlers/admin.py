"""
bot/handlers/admin.py — Admin va inspektor buyruqlari
  /stats    — Statistika
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from bot.utils.db import get_tenant_and_user, get_tenant_stats
from bot.utils.keyboards import back_keyboard
from app.core.config import settings

router = Router(name="admin")


async def _get_stats_text(tg_id: int) -> str:
    result = await get_tenant_and_user(tg_id)
    if not result:
        return "❌ Profil topilmadi."
    tenant, user = result

    if user.role not in ("admin", "super_admin", "inspector"):
        return "❌ Bu buyruq faqat admin/inspektor uchun."

    stats = await get_tenant_stats(tenant.schema_name)
    debtors_flag = "⚠️" if stats["debtors"] > 0 else "✅"
    pending_flag = "🟡" if stats["pending"] > 0 else "✅"

    return (
        f"📊 <b>{tenant.name} — Statistika</b>\n\n"
        f"👤 O'quvchilar:     <b>{stats['students']}</b>\n"
        f"👨‍🏫 O'qituvchilar:   <b>{stats['teachers']}</b>\n"
        f"📚 Faol guruhlar:  <b>{stats['groups']}</b>\n"
        f"{debtors_flag} Qarzdorlar:    <b>{stats['debtors']}</b>\n"
        f"{pending_flag} Tasdiqlash kutmoqda: <b>{stats['pending']}</b>"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    tg_id  = message.from_user.id
    result = await get_tenant_and_user(tg_id)
    if not result:
        await message.answer("❌ Profil topilmadi.")
        return
    tenant, user = result
    if user.role not in ("admin", "super_admin", "inspector"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    text = await _get_stats_text(tg_id)
    locale  = user.language_code or "uz"
    adm_url = f"{settings.FRONTEND_URL.rstrip('/')}/{locale}/admin/dashboard"
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖥 Admin paneli", web_app=WebAppInfo(url=adm_url))],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="back_start")],
        ]),
    )
