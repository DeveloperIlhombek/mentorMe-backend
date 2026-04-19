"""
bot/handlers/start.py

/start buyrug'i va deep link ishlov berish.

Deep link formatlari:
  /start                          — oddiy kirish
  /start tenant_SLUG              — tenant ma'lum (login sahifasida avtomatik to'ldiriladi)
  /start parent_STUDENTID_CODE    — ota-ona farzandiga bog'lanish
  /start inv_TENANT_CODE          — invite kodi bilan ro'yxatdan o'tish

/help, /menu — qo'shimcha buyruqlar
"""
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

from app.core.config import settings
from bot.utils.db import get_tenant_and_user
from bot.utils.keyboards import start_keyboard, help_keyboard, back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="start")

MONTH_UZ = [
    "", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]


def _webapp_url(path: str = "") -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}{path}" if path else base


# ── /start ────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    user      = message.from_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    tg_id     = user.id

    # Deep link parametrini olish
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""

    # ── parent_STUDENTID_CODE ──────────────────────────────────────────
    if args.startswith("parent_"):
        await _handle_parent_deep_link(message, args, tg_id)
        return

    # ── tenant_SLUG ──────────────────────────────────────────────────
    if args.startswith("tenant_"):
        tenant_slug = args[7:]
        await _handle_tenant_start(message, full_name, tg_id, tenant_slug)
        return

    # ── inv_TENANT_CODE ───────────────────────────────────────────────
    if args.startswith("inv_"):
        parts = args[4:].split("_", 1)
        if len(parts) == 2:
            await _handle_invite_code(message, full_name, tg_id, parts[0], parts[1])
            return

    # ── Oddiy /start ──────────────────────────────────────────────────
    await _handle_plain_start(message, full_name, tg_id)


async def _handle_plain_start(message: Message, full_name: str, tg_id: int):
    """Oddiy /start — foydalanuvchi ro'yxatda bo'lsa rol menusini, bo'lmasa umumiy menyuni ko'rsatadi."""
    db_result = await get_tenant_and_user(tg_id)

    if db_result:
        tenant, user = db_result
        role = user.role
        locale = user.language_code or "uz"
        text = (
            f"👋 Assalomu alaykum, <b>{full_name}</b>!\n\n"
            f"🏢 <b>{tenant.name}</b> ta'lim markazi\n"
            f"👤 Rol: <b>{_role_label(role)}</b>\n\n"
            f"Panel uchun quyidagi tugmani bosing:"
        )
        await message.answer(text, reply_markup=start_keyboard(role, locale))
    else:
        # Yangi foydalanuvchi — umumiy menyu
        text = (
            f"👋 Assalomu alaykum, <b>{full_name}</b>!\n\n"
            f"🎓 <b>EduSaaS</b> — zamonaviy ta'lim markazi platformasi.\n\n"
            f"📱 Mini ilovani ochish uchun quyidagi tugmani bosing.\n"
            f"📋 Ro'yxatdan o'tish uchun ta'lim markaz adminiga murojaat qiling."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📱 EduSaaS'ni ochish",
                web_app=WebAppInfo(url=_webapp_url("/uz/login")),
            )],
            [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")],
        ])
        await message.answer(text, reply_markup=keyboard)


async def _handle_tenant_start(message: Message, full_name: str, tg_id: int, tenant_slug: str):
    """tenant_SLUG — login sahifasini tenant hint bilan ochish."""
    login_url = _webapp_url(f"/uz/login?tenant={tenant_slug}")
    db_result = await get_tenant_and_user(tg_id)

    if db_result:
        tenant, user = db_result
        role = user.role
        locale = user.language_code or "uz"
        text = (
            f"👋 Assalomu alaykum, <b>{full_name}</b>!\n\n"
            f"🏢 <b>{tenant.name}</b> ta'lim markazi\n"
            f"👤 Rol: <b>{_role_label(role)}</b>"
        )
        await message.answer(text, reply_markup=start_keyboard(role, locale))
    else:
        text = (
            f"👋 <b>{full_name}</b>, xush kelibsiz!\n\n"
            f"Ta'lim markaziga kirish uchun quyidagi tugmani bosing:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔐 Kirish",
                web_app=WebAppInfo(url=login_url),
            )],
        ])
        await message.answer(text, reply_markup=keyboard)


async def _handle_parent_deep_link(message: Message, args: str, tg_id: int):
    """
    parent_STUDENTID_CODE — ota-ona farzandiga bog'lanish.
    Format: parent_<uuid>_<PRN-CODE>
    """
    # student_id va kodni ajratish
    parts = args[7:].rsplit("_", 2)
    # args = "parent_UUID_PRN-CODE"
    # "UUID_PRN-CODE" → split on last "_PRN-" occurrence is tricky
    # Better: args[7:] = "UUID_PRN-CODE", split by first "_PRN-"
    rest = args[7:]  # "8b449ba7-e55f-...-abc_PRN-ABC123"
    # UUID is 36 chars, then "_", then code
    if len(rest) > 37 and rest[36] == "_":
        student_id_str = rest[:36]
        invite_code    = rest[37:]
    else:
        await message.answer(
            "❌ Noto'g'ri havola formati.\n"
            "Admin bilan bog'laning va yangi havola so'rang."
        )
        return

    # Ota-ona ro'yxatda bormi?
    db_result = await get_tenant_and_user(tg_id)
    if not db_result:
        # Yangi foydalanuvchi — onboarding sahifaga yo'naltirish
        onboarding_url = _webapp_url(f"/uz/parent/onboarding?code={invite_code}")
        text = (
            "👋 Siz ta'lim markazi platformasiga taklif qilindingiz!\n\n"
            "Farzandingizga bog'lanish uchun quyidagi tugmani bosing:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔗 Farzandga bog'lanish",
                web_app=WebAppInfo(url=onboarding_url),
            )],
        ])
        await message.answer(text, reply_markup=keyboard)
        return

    tenant, user = db_result
    if user.role not in ("parent",):
        await message.answer(
            "❌ Bu havola faqat ota-onalar uchun.\n"
            f"Sizning rolingiz: {_role_label(user.role)}"
        )
        return

    # Kodni Redis/memory'dan tekshirish va bog'lash
    from app.core.invite_store import get_invite, delete_invite
    from sqlalchemy import select, text as sqltext
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.student import Student
    from app.models.tenant.user import User as TUser
    import uuid

    tenant_slug = tenant.slug if hasattr(tenant, "slug") else tenant.schema_name
    student_id_val = await get_invite(tenant_slug, invite_code)

    if not student_id_val or student_id_val != student_id_str:
        # Fallback — to'g'ridan-to'g'ri onboarding sahifasiga yo'naltirish
        onboarding_url = _webapp_url(f"/uz/parent/onboarding?code={invite_code}")
        await message.answer(
            "🔗 Farzandga bog'lanish uchun quyidagi tugmani bosing:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔗 Bog'lanish",
                    web_app=WebAppInfo(url=onboarding_url),
                )
            ]]),
        )
        return

    schema = tenant.schema_name
    async with AsyncSessionLocal() as session:
        await session.execute(sqltext(f'SET search_path TO "{schema}", public'))
        student = (await session.execute(
            select(Student).where(Student.id == uuid.UUID(student_id_str))
        )).scalar_one_or_none()
        if not student:
            await message.answer("❌ O'quvchi topilmadi.")
            return
        student.parent_id = user.id
        await session.commit()
        child_user = (await session.execute(
            select(TUser).where(TUser.id == student.user_id)
        )).scalar_one_or_none()

    await delete_invite(tenant_slug, invite_code)
    child_name = f"{child_user.first_name} {child_user.last_name or ''}".strip() if child_user else "Farzand"
    await message.answer(
        f"✅ <b>Muvaffaqiyatli bog'landi!</b>\n\n"
        f"👧 Farzandingiz: <b>{child_name}</b>\n\n"
        f"Endi davomat, to'lov va bildirishnomalarni kuzatishingiz mumkin.",
        reply_markup=start_keyboard("parent", user.language_code or "uz"),
    )


async def _handle_invite_code(
    message: Message, full_name: str, tg_id: int,
    tenant_slug: str, code: str,
):
    """inv_TENANT_CODE — invite kodi bilan ro'yxatdan o'tish."""
    login_url = _webapp_url(f"/uz/login?tenant={tenant_slug}&invite={code}")
    text = (
        f"👋 <b>{full_name}</b>, ta'lim markaziga taklif qilindingiz!\n\n"
        f"Ro'yxatdan o'tish va panelni ochish uchun tugmani bosing:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Ro'yxatdan o'tish",
            web_app=WebAppInfo(url=login_url),
        )],
    ])
    await message.answer(text, reply_markup=keyboard)


# ── /help ─────────────────────────────────────────────────────────────────

@router.message(Command("help", "menu"))
async def cmd_help(message: Message):
    tg_id  = message.from_user.id
    result = await get_tenant_and_user(tg_id)
    role   = result[1].role if result else None
    await _show_help(message, role)


async def _show_help(target, role: str | None):
    base_cmds = (
        "/start — Bosh menyu\n"
        "/help  — Yordam\n"
    )
    role_cmds = ""
    if role == "student":
        role_cmds = (
            "/profile    — Profil + XP\n"
            "/attendance — Davomat\n"
            "/balance    — Balans\n"
            "/streak     — Streak\n"
        )
    elif role == "teacher":
        role_cmds = (
            "/mygroups — Guruhlarim\n"
            "/today    — Bugungi darslar\n"
        )
    elif role == "parent":
        role_cmds = (
            "/children — Farzandlarim\n"
            "/pay      — To'lov\n"
        )
    elif role in ("admin", "super_admin"):
        role_cmds = (
            "/stats — Statistika\n"
        )

    text = (
        "📋 <b>EduSaaS Bot — Buyruqlar</b>\n\n"
        f"{base_cmds}"
        + (f"\n<b>Sizning buyruqlaringiz:</b>\n{role_cmds}" if role_cmds else "")
        + "\n\n<b>Bildirishnomalar:</b>\n"
        "• 📋 Davomat (kelganda/kelmanganda)\n"
        "• 💰 To'lov eslatmalari\n"
        "• ⭐ Yangi XP va yutuqlar\n"
        "• 📅 Dars eslatmalari\n"
        "• ✅ Tasdiqlash xabarlari"
    )
    await target.answer(text, reply_markup=help_keyboard())


# ── Callback querylar ─────────────────────────────────────────────────────

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    tg_id  = callback.from_user.id
    result = await get_tenant_and_user(tg_id)
    role   = result[1].role if result else None
    await _show_help(callback.message, role)
    await callback.answer()


@router.callback_query(F.data == "back_start")
async def cb_back_start(callback: CallbackQuery):
    tg_id     = callback.from_user.id
    full_name = f"{callback.from_user.first_name} {callback.from_user.last_name or ''}".strip()
    result    = await get_tenant_and_user(tg_id)
    if result:
        tenant, user = result
        role = user.role
        locale = user.language_code or "uz"
        text = (
            f"👤 <b>{full_name}</b> — {_role_label(role)}\n"
            f"🏢 {tenant.name}"
        )
        await callback.message.edit_text(text, reply_markup=start_keyboard(role, locale))
    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    from bot.handlers.student import _get_profile_text
    tg_id = callback.from_user.id
    data  = await _get_profile_text(tg_id)
    await callback.message.answer(data, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "attendance")
async def cb_attendance(callback: CallbackQuery):
    from bot.handlers.student import _get_attendance_text
    tg_id = callback.from_user.id
    data  = await _get_attendance_text(tg_id)
    await callback.message.answer(data, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "children")
async def cb_children(callback: CallbackQuery):
    from bot.handlers.parent import _get_children_text
    tg_id = callback.from_user.id
    data  = await _get_children_text(tg_id)
    await callback.message.answer(data, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "mygroups")
async def cb_mygroups(callback: CallbackQuery):
    from bot.handlers.teacher import _get_groups_text
    tg_id = callback.from_user.id
    data  = await _get_groups_text(tg_id)
    await callback.message.answer(data, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "today")
async def cb_today(callback: CallbackQuery):
    from bot.handlers.teacher import _get_today_text
    tg_id = callback.from_user.id
    data  = await _get_today_text(tg_id)
    await callback.message.answer(data, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    from bot.handlers.admin import _get_stats_text
    tg_id = callback.from_user.id
    data  = await _get_stats_text(tg_id)
    await callback.message.answer(data, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "payments")
async def cb_payments(callback: CallbackQuery):
    tg_id = callback.from_user.id
    result = await get_tenant_and_user(tg_id)
    if not result:
        await callback.answer("❌ Profil topilmadi", show_alert=True)
        return
    _, user = result
    locale = user.language_code or "uz"
    url = f"{settings.FRONTEND_URL.rstrip('/')}/{locale}/parent/payments"
    await callback.message.answer(
        "💳 To'lovlar bo'limiga o'ting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💳 To'lovlar", web_app=WebAppInfo(url=url))
        ]]),
    )
    await callback.answer()


# ── Yordam funksiyasi ─────────────────────────────────────────────────────

def _role_label(role: str) -> str:
    return {
        "student":     "O'quvchi",
        "teacher":     "O'qituvchi",
        "parent":      "Ota-ona",
        "inspector":   "Inspektor",
        "admin":       "Admin",
        "super_admin": "Super admin",
    }.get(role, role)
