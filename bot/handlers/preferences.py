"""
bot/handlers/preferences.py

Bot komandalari:
  /preferences  — Notification kategoriyalarini toggle qilish

Critical kategoriyalar (attendance, payment, system) toggle qilinmaydi.
"""
import logging
from typing import Optional, Tuple

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from sqlalchemy import select, text as sqltext

from app.core.database import AsyncSessionLocal
from bot.utils.db import get_tenant_and_user

logger = logging.getLogger(__name__)
router = Router(name="preferences")


# Foydalanuvchi toggle qilishi mumkin bo'lgan kategoriyalar
TOGGLABLE_CATEGORIES: list[Tuple[str, str]] = [
    ("lesson",       "📚 Dars eslatmalari"),
    ("grade",        "📊 Yangi baholar"),
    ("kpi",          "📈 KPI hisoboti"),
    ("progress",     "📈 Progress eslatmalari"),
    ("broadcast",    "📢 E'lonlar"),
    ("subscription", "⏳ Subscription"),
]


async def _load_pref(tenant_schema: str, user_id) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        await session.execute(sqltext(f'SET search_path TO "{tenant_schema}", public'))
        row = (await session.execute(sqltext("""
            SELECT telegram_enabled, in_app_enabled, disabled_categories,
                   quiet_hours_start, quiet_hours_end
            FROM notification_preferences
            WHERE user_id = :uid
        """), {"uid": str(user_id)})).first()
        if not row:
            await session.execute(sqltext("""
                INSERT INTO notification_preferences (user_id) VALUES (:uid)
            """), {"uid": str(user_id)})
            await session.commit()
            return {
                "telegram_enabled": True, "in_app_enabled": True,
                "disabled_categories": [], "quiet_hours_start": "22:00", "quiet_hours_end": "07:00",
            }
        te, ia, dc, qs, qe = row
        return {
            "telegram_enabled": te, "in_app_enabled": ia,
            "disabled_categories": list(dc or []),
            "quiet_hours_start": qs.strftime("%H:%M") if qs else None,
            "quiet_hours_end":   qe.strftime("%H:%M") if qe else None,
        }


async def _toggle_category(tenant_schema: str, user_id, category: str) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(sqltext(f'SET search_path TO "{tenant_schema}", public'))
        row = (await session.execute(sqltext("""
            SELECT disabled_categories FROM notification_preferences WHERE user_id = :uid
        """), {"uid": str(user_id)})).first()
        if not row:
            disabled = [category]
            await session.execute(sqltext("""
                INSERT INTO notification_preferences (user_id, disabled_categories)
                VALUES (:uid, :dc)
            """), {"uid": str(user_id), "dc": disabled})
        else:
            disabled = list(row[0] or [])
            if category in disabled:
                disabled.remove(category)
            else:
                disabled.append(category)
            await session.execute(sqltext("""
                UPDATE notification_preferences
                SET disabled_categories = :dc, updated_at = NOW()
                WHERE user_id = :uid
            """), {"uid": str(user_id), "dc": disabled})
        await session.commit()
        return {"disabled_categories": disabled}


def _build_keyboard(pref: dict) -> InlineKeyboardMarkup:
    disabled = set(pref.get("disabled_categories") or [])
    rows = []
    for cat, label in TOGGLABLE_CATEGORIES:
        prefix = "✅" if cat not in disabled else "⬜️"
        rows.append([InlineKeyboardButton(
            text=f"{prefix} {label}",
            callback_data=f"pref:toggle:{cat}",
        )])
    rows.append([InlineKeyboardButton(text="✖️ Yopish", callback_data="pref:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_message(pref: dict) -> str:
    qs = pref.get("quiet_hours_start") or "—"
    qe = pref.get("quiet_hours_end") or "—"
    return (
        "<b>🔔 Bildirishnoma sozlamalari</b>\n\n"
        "Quyidagi kategoriyalarni yoqish/o'chirish mumkin.\n"
        "<i>Davomat va to'lov bildirishnomalari majburiy — ularni o'chirib bo'lmaydi.</i>\n\n"
        f"🌙 Tinch soatlar: <b>{qs} – {qe}</b>"
    )


@router.message(Command("preferences"))
async def cmd_preferences(message: Message):
    tg_id = message.from_user.id
    res = await get_tenant_and_user(tg_id)
    if not res:
        await message.answer("❌ Profil topilmadi. Avval admin sizni tizimga qo'shsin.")
        return
    tenant, user = res
    pref = await _load_pref(tenant.schema_name, user.id)
    await message.answer(
        _format_message(pref),
        reply_markup=_build_keyboard(pref),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("pref:toggle:"))
async def cb_toggle(callback: CallbackQuery):
    cat = callback.data.split(":")[2]
    valid = {c for c, _ in TOGGLABLE_CATEGORIES}
    if cat not in valid:
        await callback.answer("Noto'g'ri kategoriya", show_alert=True)
        return

    tg_id = callback.from_user.id
    res = await get_tenant_and_user(tg_id)
    if not res:
        await callback.answer("Profil topilmadi", show_alert=True)
        return
    tenant, user = res
    await _toggle_category(tenant.schema_name, user.id, cat)
    pref = await _load_pref(tenant.schema_name, user.id)

    try:
        await callback.message.edit_text(
            _format_message(pref),
            reply_markup=_build_keyboard(pref),
        )
    except Exception:
        pass
    await callback.answer("✓ Saqlandi")


@router.callback_query(lambda c: c.data == "pref:close")
async def cb_close(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
