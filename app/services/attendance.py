"""
app/services/attendance.py

Davomat biznes logika:
  - Bulk kiritish (bir guruh, bir kun)
  - XP berish (present/late uchun +10 XP)
  - Ota-onaga bildirishnoma (absent uchun)
  - Streak hisoblash
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import (
    Attendance,
    GamificationProfile,
    Group,
    Notification,
    Student,
    User,
    XpTransaction,
)
from app.schemas.attendance import AttendanceBulkCreate

# XP miqdorlari (TZ dan)
XP_LESSON_ATTENDED = 10

# XP darajalari (TZ dan)
XP_LEVELS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500]


def _calc_level(total_xp: int) -> int:
    level = 1
    for i, threshold in enumerate(XP_LEVELS):
        if total_xp >= threshold:
            level = i + 1
    return min(level, 10)


# ─── asosiy funksiyalar ───────────────────────────────────────────────

async def bulk_create(
    db: AsyncSession,
    data: AttendanceBulkCreate,
    teacher_id: Optional[uuid.UUID],
    tenant_slug: Optional[str] = None,
) -> dict:
    """
    Bir guruh, bir kun uchun davomat kiritish.
    - Mavjud bo'lsa yangilaydi (upsert)
    - present/late → XP beradi
    - absent → ota-onaga bildirishnoma
    """
    created = 0
    xp_count = 0

    for item in data.records:
        # Upsert: mavjud yozuvni yangilash yoki yangi yaratish
        stmt = select(Attendance).where(
            and_(
                Attendance.student_id == item.student_id,
                Attendance.group_id   == data.group_id,
                Attendance.date       == data.date,
            )
        )
        att = (await db.execute(stmt)).scalar_one_or_none()

        if att:
            att.status = item.status
            att.note   = item.note
        else:
            att = Attendance(
                student_id=item.student_id,
                group_id=data.group_id,
                teacher_id=teacher_id,
                date=data.date,
                status=item.status,
                note=item.note,
            )
            db.add(att)
            await db.flush()
            created += 1

        # XP: kelgan yoki kechikkan o'quvchiga
        if item.status in ("present", "late"):
            await _award_xp(
                db,
                student_id=item.student_id,
                amount=XP_LESSON_ATTENDED,
                reason="lesson_attended",
                reference_id=att.id,
                tenant_slug=tenant_slug,
            )
            xp_count += 1

        # Absent: ota-onaga xabar
        elif item.status == "absent":
            await _notify_parent_absent(db, item.student_id, data.group_id, data.date)

    await db.commit()

    return {
        "created": created,
        "xp_awarded": xp_count,
        "date": data.date.isoformat(),
        "group_id": str(data.group_id),
    }


async def get_by_group_date(
    db: AsyncSession,
    group_id: uuid.UUID,
    date_val: date,
) -> List[dict]:
    """Guruhning ma'lum kkundagi davomati."""
    stmt = (
        select(Attendance, Student, User)
        .join(Student, Attendance.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(
            and_(
                Attendance.group_id == group_id,
                Attendance.date     == date_val,
            )
        )
        .order_by(User.first_name)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": str(att.id),
            "student_id": str(att.student_id),
            "status": att.status,
            "note": att.note,
            "parent_notified": att.parent_notified,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
        for att, student, user in rows
    ]


async def get_student_history(
    db: AsyncSession,
    student_id: uuid.UUID,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> dict:
    """O'quvchining davomat tarixi + oy statistikasi."""
    from app.models.tenant.group import Group

    stmt = (
        select(Attendance, Group)
        .outerjoin(Group, Attendance.group_id == Group.id)
        .where(Attendance.student_id == student_id)
    )

    if month and year:
        stmt = stmt.where(
            and_(
                extract("month", Attendance.date) == month,
                extract("year",  Attendance.date) == year,
            )
        )

    stmt = stmt.order_by(Attendance.date.desc())
    rows = (await db.execute(stmt)).all()
    records = [r for r, g in rows]

    total   = len(records)
    present = sum(1 for r in records if r.status == "present")
    absent  = sum(1 for r in records if r.status == "absent")
    late    = sum(1 for r in records if r.status == "late")
    excused = sum(1 for r in records if r.status == "excused")
    pct     = round((present + late) / total * 100, 1) if total else 0.0

    return {
        "records": [
            {
                "id":         str(r.id),
                "date":       r.date.isoformat(),
                "status":     r.status,
                "group_id":   str(r.group_id) if r.group_id else None,
                "group_name": g.name if g else None,
                "arrived_at": r.arrived_at.strftime("%H:%M") if r.arrived_at else None,
                "note":       r.note,
            }
            for r, g in rows
        ],
        "summary": {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "attendance_percent": pct,
        },
    }


async def get_summary(
    db: AsyncSession,
    group_id: uuid.UUID,
    date_val: date,
) -> dict:
    """Guruhning bir kundagi statistikasi."""
    stmt = select(
        func.count().label("total"),
        func.count(Attendance.id).filter(Attendance.status == "present").label("present"),
        func.count(Attendance.id).filter(Attendance.status == "absent").label("absent"),
        func.count(Attendance.id).filter(Attendance.status == "late").label("late"),
        func.count(Attendance.id).filter(Attendance.status == "excused").label("excused"),
    ).where(
        and_(Attendance.group_id == group_id, Attendance.date == date_val)
    )
    row = (await db.execute(stmt)).one()

    total   = row.total   or 0
    present = row.present or 0
    absent  = row.absent  or 0
    late    = row.late    or 0
    excused = row.excused or 0
    pct     = round((present + late) / total * 100, 1) if total else 0.0

    return {
        "group_id": str(group_id),
        "date": date_val.isoformat(),
        "present": present,
        "absent": absent,
        "late": late,
        "excused": excused,
        "total": total,
        "percent": pct,
    }


# ─── ichki yordamchilar ───────────────────────────────────────────────

async def _award_xp(
    db: AsyncSession,
    student_id: uuid.UUID,
    amount: int,
    reason: str,
    reference_id: Optional[uuid.UUID] = None,
    tenant_slug: Optional[str] = None,
) -> None:
    """
    XP berish:
    1. xp_transactions ga yozuv qo'shish
    2. gamification_profiles ni yangilash (total_xp, weekly_xp, level, streak)
    """
    # 1. Tranzaksiya
    db.add(XpTransaction(
        student_id=student_id,
        amount=amount,
        reason=reason,
        reference_id=reference_id,
    ))

    # 2. Profil yangilash
    stmt = select(GamificationProfile).where(
        GamificationProfile.student_id == student_id
    )
    profile = (await db.execute(stmt)).scalar_one_or_none()

    if not profile:
        profile = GamificationProfile(student_id=student_id)
        db.add(profile)
        await db.flush()

    profile.total_xp  += amount
    profile.weekly_xp += amount
    profile.current_level = _calc_level(profile.total_xp)

    # Streak hisoblash
    today = date.today()
    if profile.last_activity_date:
        diff = (today - profile.last_activity_date).days
        if diff == 1:
            profile.current_streak += 1
            profile.max_streak = max(profile.max_streak, profile.current_streak)
        elif diff > 1:
            profile.current_streak = 1
    else:
        profile.current_streak = 1

    profile.last_activity_date = today


async def _notify_parent_absent(
    db: AsyncSession,
    student_id: uuid.UUID,
    group_id: uuid.UUID,
    att_date: date,
) -> None:
    """
    Kelmagan o'quvchining ota-onasiga bildirishnoma yaratish.
    Telegram bot keyinchalik bu yozuvlarni o'qib yuboradi.
    """
    # O'quvchini olish
    stmt = select(Student).where(Student.id == student_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student or not student.parent_id:
        return  # Parent bog'lanmagan — xabar yuborib bo'lmaydi

    # O'quvchi ismi
    user_stmt = select(User).where(User.id == student.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    student_name = f"{user.first_name} {user.last_name or ''}".strip() if user else "O'quvchi"

    # Guruh nomi
    group_stmt = select(Group).where(Group.id == group_id)
    group = (await db.execute(group_stmt)).scalar_one_or_none()
    group_name = group.name if group else "Guruh"

    db.add(Notification(
        user_id=student.parent_id,
        type="absence_alert",
        title=f"{student_name} darsga kelmadi",
        body=(
            f"{student_name} bugun "
            f"({att_date.strftime('%d.%m.%Y')}) "
            f"{group_name} darsiga kelmadi."
        ),
        data={
            "student_id": str(student_id),
            "group_id":   str(group_id),
            "date":       att_date.isoformat(),
        },
        channel="telegram",
    ))
