"""
bot/handlers/parent.py — Ota-ona buyruqlari
  /children — Farzandlarim
  /pay      — To'lov havola
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from bot.utils.db import get_tenant_and_user, get_parent_children
from bot.utils.keyboards import back_keyboard
from app.core.config import settings

router = Router(name="parent")


async def _get_children_text(tg_id: int) -> str:
    result = await get_tenant_and_user(tg_id)
    if not result:
        return "❌ Profil topilmadi."
    tenant, user = result

    rows = await get_parent_children(tenant.schema_name, user.id)
    if not rows:
        return (
            "👨‍👧 <b>Farzandlar topilmadi.</b>\n\n"
            "Admin bergan invite kodi orqali farzandingizga bog'laning."
        )

    lines = ["👨‍👧 <b>Farzandlaringiz:</b>\n"]
    for student, child_user in rows:
        bal = float(student.balance)
        if bal > 0:
            bal_str = f"✅ +{bal:,.0f} so'm"
        elif bal < 0:
            bal_str = f"⚠️ Qarz: {abs(bal):,.0f} so'm"
        else:
            bal_str = "💰 0 so'm"
        status = "Faol" if student.is_active else "Nofaol"
        lines.append(
            f"• <b>{child_user.first_name} {child_user.last_name or ''}</b> [{status}]\n"
            f"  {bal_str}"
        )

    return "\n".join(lines)


@router.message(Command("children"))
async def cmd_children(message: Message):
    text = await _get_children_text(message.from_user.id)
    await message.answer(text, reply_markup=back_keyboard())


@router.message(Command("pay"))
async def cmd_pay(message: Message):
    tg_id = message.from_user.id
    result = await get_tenant_and_user(tg_id)
    locale = "uz"
    if result:
        _, user = result
        locale = user.language_code or "uz"

    pay_url = f"{settings.FRONTEND_URL.rstrip('/')}/{locale}/parent/payments"
    await message.answer(
        "💳 <b>To'lov qilish</b>\n\n"
        "To'lovlar sahifasiga o'tish uchun quyidagi tugmani bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💳 To'lovlar", web_app=WebAppInfo(url=pay_url))
        ]]),
    )
