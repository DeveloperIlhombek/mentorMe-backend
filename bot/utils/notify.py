"""
bot/utils/notify.py

Bildirishnoma yuborish servisi.
Celery tasks yoki API endpointlardan chaqiriladi.

Asosiy funksiyalar:
  send_to_user(telegram_id, text)              — har qanday foydalanuvchiga
  notify_attendance(student_id, status, ...)   — davomat bildirishnomasi
  notify_payment_reminder(student_id, amount)  — to'lov eslatmasi
  notify_student_approved(student_id)          — tasdiqlash xabari
  notify_new_pending_to_admin(tenant_schema)   — adminga yangi so'rov
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def _get_bot():
    """Bot instance singleton."""
    from app.webhooks.bot import get_bot
    return get_bot()


async def send_to_user(telegram_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """
    Berilgan Telegram ID ga xabar yuborish.
    Qaytaradi: True — muvaffaqiyatli, False — xato.
    """
    try:
        bot = await _get_bot()
        await bot.send_message(chat_id=telegram_id, text=text, parse_mode=parse_mode)
        return True
    except Exception as e:
        logger.warning(f"Xabar yuborib bo'lmadi tg_id={telegram_id}: {e}")
        return False


async def notify_attendance(
    tenant_schema: str,
    student_id,
    status: str,          # present | absent | late | excused
    group_name: str = "",
    lesson_date: str = "",
    xp_earned: int = 0,
) -> None:
    """O'quvchi va ota-onasiga davomat bildirishnomasi."""
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.student import Student
    from app.models.tenant.user import User

    STATUS_TEXT = {
        "present": ("✅", "Darsga keldingiz", "Keldi"),
        "absent":  ("❌", "Darsga kelmadingiz", "Kelmadi"),
        "late":    ("⏰", "Darsga kechikdingiz", "Kechikdi"),
        "excused": ("📝", "Uzrli sabab qayd etildi", "Uzrli"),
    }
    emoji, student_msg, parent_msg = STATUS_TEXT.get(status, ("📋", status, status))

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))

        import uuid
        sid = uuid.UUID(str(student_id)) if not isinstance(student_id, uuid.UUID) else student_id
        student = (await session.execute(select(Student).where(Student.id == sid))).scalar_one_or_none()
        if not student:
            return

        student_user = (await session.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
        parent_user  = (await session.execute(select(User).where(User.id == student.parent_id))).scalar_one_or_none() if student.parent_id else None

    date_str = lesson_date or "Bugun"
    group_str = f" ({group_name})" if group_name else ""

    # O'quvchiga
    if student_user and student_user.telegram_id:
        stu_text = (
            f"{emoji} <b>{student_msg}</b>{group_str}\n"
            f"📅 {date_str}"
        )
        if status == "present" and xp_earned:
            stu_text += f"\n⭐ +{xp_earned} XP qo'shildi!"
        await send_to_user(student_user.telegram_id, stu_text)

    # Ota-onaga
    if parent_user and parent_user.telegram_id:
        child_name = f"{student_user.first_name}" if student_user else "Farzandingiz"
        par_text = (
            f"{emoji} <b>{child_name}: {parent_msg}</b>{group_str}\n"
            f"📅 {date_str}"
        )
        await send_to_user(parent_user.telegram_id, par_text)


async def notify_payment_reminder(
    tenant_schema: str,
    student_id,
    amount: float,
    due_day: int = 1,
) -> None:
    """O'quvchi va ota-onasiga to'lov eslatmasi."""
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.student import Student
    from app.models.tenant.user import User
    import uuid

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        sid = uuid.UUID(str(student_id)) if not isinstance(student_id, uuid.UUID) else student_id
        student     = (await session.execute(select(Student).where(Student.id == sid))).scalar_one_or_none()
        if not student:
            return
        student_user = (await session.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
        parent_user  = (await session.execute(select(User).where(User.id == student.parent_id))).scalar_one_or_none() if student.parent_id else None

    text_msg = (
        f"💰 <b>To'lov eslatmasi</b>\n\n"
        f"Oylik to'lov: <b>{amount:,.0f} so'm</b>\n"
        f"To'lov kuni: har oyning <b>{due_day}-kuni</b>\n\n"
        f"Iltimos, o'z vaqtida to'lovni amalga oshiring."
    )

    for u in filter(None, [student_user, parent_user]):
        if u and u.telegram_id:
            await send_to_user(u.telegram_id, text_msg)


async def notify_student_approved(
    tenant_schema: str,
    student_id,
) -> None:
    """O'quvchi tasdiqlanganda xabar yuborish."""
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.student import Student
    from app.models.tenant.user import User
    import uuid

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        sid = uuid.UUID(str(student_id)) if not isinstance(student_id, uuid.UUID) else student_id
        student     = (await session.execute(select(Student).where(Student.id == sid))).scalar_one_or_none()
        if not student:
            return
        student_user = (await session.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()

    if student_user and student_user.telegram_id:
        await send_to_user(
            student_user.telegram_id,
            f"✅ <b>Profilingiz tasdiqlandi!</b>\n\n"
            f"Endi to'liq panel imkoniyatlariga ega bo'ldingiz.\n"
            f"/start → panelni oching.",
        )


async def notify_new_pending_to_admins(
    tenant_schema: str,
    student_name: str,
    created_by_name: str = "",
) -> None:
    """Admin(lar)ga yangi tasdiqlash so'rovi haqida xabar."""
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.user import User

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        admins = (await session.execute(
            select(User).where(User.role.in_(["admin", "super_admin"]))
        )).scalars().all()

    by_str  = f" ({created_by_name})" if created_by_name else " (O'qituvchi/inspektor)"
    msg = (
        f"🔔 <b>Yangi tasdiqlash so'rovi</b>\n\n"
        f"O'quvchi: <b>{student_name}</b>\n"
        f"Kim qo'shdi:{by_str}\n\n"
        f"/stats — statistikani ko'ring\n"
        f"Admin panelida tasdiqlang."
    )
    for admin in admins:
        if admin.telegram_id:
            await send_to_user(admin.telegram_id, msg)


async def notify_xp_earned(
    telegram_id: int,
    xp: int,
    reason: str,
    new_level: Optional[int] = None,
) -> None:
    """O'quvchiga XP olganini bildirish."""
    text = f"⭐ <b>+{xp} XP</b> — {reason}"
    if new_level:
        text = f"🎉 <b>Yangi daraja: {new_level}!</b>\n" + text
    await send_to_user(telegram_id, text)


async def notify_group_enrollment(
    tenant_schema: str,
    student_name: str,
    group_name: str,
    action: str,              # "added" | "removed" | "pending"
    by_name: str = "",
    by_role: str = "",
) -> None:
    """
    Admin va inspektorlarga o'quvchi guruhga qo'shilganda/chiqarilganda xabar.
      action="added"   — qo'shildi
      action="removed" — chiqarildi
      action="pending" — teacher so'rovi, tasdiq kerak
    """
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal
    from app.models.tenant.user import User

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        recipients = (await session.execute(
            select(User).where(User.role.in_(["admin", "super_admin", "inspector"]))
        )).scalars().all()

    by_str = f" ({by_name}, {by_role})" if by_name else ""

    if action == "added":
        emoji, verb = "➕", f"<b>{student_name}</b> guruhga qo'shildi"
    elif action == "removed":
        emoji, verb = "➖", f"<b>{student_name}</b> guruhdan chiqarildi"
    else:
        emoji, verb = "🔔", f"<b>{student_name}</b> guruhga qo'shish so'rovi"

    msg = (
        f"{emoji} <b>Guruh o'zgarishi</b>\n\n"
        f"Guruh: <b>{group_name}</b>\n"
        f"{verb}{by_str}\n"
    )
    if action == "pending":
        msg += "\nAdmin panelida tasdiqlang."

    for user in recipients:
        if user.telegram_id:
            await send_to_user(user.telegram_id, msg)
