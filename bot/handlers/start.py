"""
bot/handlers/start.py

/start — birinchi xabar.
Foydalanuvchi rol bo'yicha to'g'ri menuga yo'naltiriladi.
"""
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo,
)

router = Router(name="start")

# Frontendning URL (ngrok yoki production)
WEBAPP_URL = "https://your-app.com"  # .env dan olinadi


@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    /start — barcha foydalanuvchilar uchun.
    Telegram ID bo'yicha rol aniqlanadi.
    """
    user = message.from_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()

    text = (
        f"👋 Assalomu alaykum, <b>{full_name}</b>!\n\n"
        f"🎓 <b>EduSaaS</b> — ta'lim markazlari platformasiga xush kelibsiz.\n\n"
        f"Quyidagi tugmalar orqali panel ga kiring:"
    )

    # Mini App tugmasi
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Panelni ochish",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )],
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")],
    ])

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "help")
async def show_help(callback):
    await callback.message.answer(
        "📋 <b>EduSaaS Bot</b>\n\n"
        "Bot quyidagi bildirishnomalarni yuboradi:\n"
        "• 📋 Davomat (kelganda/kelmanganda)\n"
        "• 💰 To'lov eslatmalari\n"
        "• ⭐ Yangi XP va yutuqlar\n"
        "• 📅 Dars eslatmalari\n\n"
        "<b>Buyruqlar:</b>\n"
        "/start — Bosh menyu\n"
        "/profile — Profil\n"
        "/attendance — Davomat\n"
        "/balance — Balans\n"
    )
    await callback.answer()
