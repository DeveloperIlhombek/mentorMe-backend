"""bot/handlers/parent.py — Ota-ona buyruqlari"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.utils.db import get_tenant_by_telegram_id

router = Router(name="parent")


@router.message(Command("children"))
async def cmd_children(message: Message):
    tg_id  = message.from_user.id
    result = await get_tenant_by_telegram_id(tg_id)
    if not result:
        await message.answer("❌ Profil topilmadi.")
        return
    tenant, user = result

    from sqlalchemy import select, text, and_
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.student import Student
    from app.models.tenant.user import User as TUser
    schema = tenant.schema_name
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        stmt = (
            select(Student, TUser)
            .join(TUser, Student.user_id == TUser.id)
            .where(Student.parent_id == user.id)
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        await message.answer("👨‍👧 Farzandlar topilmadi.\nAdmin bilan bog'lang.")
        return

    lines = ["👨‍👧 <b>Farzandlaringiz:</b>\n"]
    for st, u in rows:
        bal = float(st.balance)
        bal_str = f"✅ {bal:,.0f}" if bal >= 0 else f"⚠️ Qarz: {abs(bal):,.0f}"
        lines.append(f"• <b>{u.first_name} {u.last_name or ''}</b>\n  Balans: {bal_str} so'm")

    await message.answer("\n".join(lines))


@router.message(Command("pay"))
async def cmd_pay(message: Message):
    await message.answer(
        "💳 <b>To'lov qilish</b>\n\n"
        "To'lov Click orqali amalga oshiriladi.\n"
        "/start → Panelni ochish → To'lovlar"
    )
