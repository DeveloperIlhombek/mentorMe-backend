"""
bot/utils/keyboards.py

Inline va Reply klaviaturalar — rol bo'yicha.
"""
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    WebAppInfo,
)
from app.core.config import settings


def webapp_button(path: str = "") -> InlineKeyboardButton:
    """Mini App tugmasi."""
    url = settings.FRONTEND_URL.rstrip("/")
    if path:
        url = f"{url}{path}"
    return InlineKeyboardButton(text="📱 Panelni ochish", web_app=WebAppInfo(url=url))


# ── Inline klaviaturalar ────────────────────────────────────────────────

def start_keyboard(role: str | None = None, locale: str = "uz") -> InlineKeyboardMarkup:
    """
    /start da ko'rsatiladigan klaviatura.
    Role bo'yicha mini app URL mos yo'lga o'tadi.
    """
    path_map = {
        "student":   f"/{locale}/student/dashboard",
        "teacher":   f"/{locale}/teacher/dashboard",
        "parent":    f"/{locale}/parent/dashboard",
        "inspector": f"/{locale}/inspector/dashboard",
        "admin":     f"/{locale}/admin/dashboard",
    }
    path = path_map.get(role or "", "")
    rows = [
        [webapp_button(path)],
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")],
    ]
    if role == "parent":
        rows.insert(1, [
            InlineKeyboardButton(text="👧 Farzandlarim", callback_data="children"),
            InlineKeyboardButton(text="💰 To'lovlar", callback_data="payments"),
        ])
    elif role == "student":
        rows.insert(1, [
            InlineKeyboardButton(text="⭐ Profil & XP", callback_data="profile"),
            InlineKeyboardButton(text="📅 Davomat", callback_data="attendance"),
        ])
    elif role == "teacher":
        rows.insert(1, [
            InlineKeyboardButton(text="📚 Guruhlarim", callback_data="mygroups"),
            InlineKeyboardButton(text="📅 Bugungi darslar", callback_data="today"),
        ])
    elif role in ("admin", "inspector"):
        rows.insert(1, [
            InlineKeyboardButton(text="📊 Statistika", callback_data="stats"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_start")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="back_start")],
    ])
