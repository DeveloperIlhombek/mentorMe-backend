"""
app/services/attendance.py

Davomat biznes logika:
  - Bulk kiritish (bir guruh, bir kun)
  - XP berish (present/late uchun +10 XP)
  - Ota-onaga bildirishnoma (absent uchun)
  - Streak hisoblash
"""
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import (
    Attendance,
    GamificationProfile,
    Group,
    Notification,
    Student,
    StudentGroup,
    User,
    XpTransaction,
)
from app.models.tenant.branch import Branch
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

async def _is_late_submission(
    db: AsyncSession,
    group: Group,
    lesson_date: date,
    submitted_at: datetime,
) -> bool:
    """
    Davomat kech kiritilganligini tekshiradi.
    Guruh jadvalidagi o'sha kunga mos dars tugash vaqti + branch deadline_hours ni oladi.
    Agar submitted_at > deadline → True (kech).
    """
    # Branch deadline soatini olish
    deadline_hours = 2  # default
    if group.branch_id:
        branch = (await db.execute(
            select(Branch).where(Branch.id == group.branch_id)
        )).scalar_one_or_none()
        if branch and hasattr(branch, "attendance_deadline_hours"):
            deadline_hours = branch.attendance_deadline_hours or 2

    # Guruh jadvalidan o'sha kuni uchun dars tugash vaqtini topish
    # schedule.day = isoweekday (1=Du...7=Ya)
    lesson_dow = lesson_date.isoweekday()
    schedule = group.schedule or []
    end_time_str = None
    for slot in schedule:
        if isinstance(slot, dict) and slot.get("day") == lesson_dow:
            end_time_str = slot.get("end")
            break

    if not end_time_str:
        # Jadvalda topilmadi → faqat 23:59 gacha bo'lsa o'z vaqtida
        lesson_end_dt = datetime.combine(lesson_date, datetime.strptime("23:59", "%H:%M").time())
        lesson_end_dt = lesson_end_dt.replace(tzinfo=submitted_at.tzinfo)
    else:
        try:
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            lesson_end_dt = datetime.combine(lesson_date, end_time)
            lesson_end_dt = lesson_end_dt.replace(tzinfo=submitted_at.tzinfo)
        except ValueError:
            lesson_end_dt = datetime.combine(lesson_date, datetime.strptime("23:59", "%H:%M").time())
            lesson_end_dt = lesson_end_dt.replace(tzinfo=submitted_at.tzinfo)

    deadline_dt = lesson_end_dt + timedelta(hours=deadline_hours)
    return submitted_at > deadline_dt


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
    - submitted_at va is_late_entry belgilanadi
    """
    created = 0
    xp_count = 0
    submitted_at = datetime.utcnow()

    # Guruhni olish (kechikish tekshiruvi uchun)
    group = (await db.execute(
        select(Group).where(Group.id == data.group_id)
    )).scalar_one_or_none()

    is_late = False
    if group:
        try:
            is_late = await _is_late_submission(db, group, data.date, submitted_at)
        except Exception:
            is_late = False  # migration hali bajarilmagan bo'lsa xavfsiz fallback

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
            att.status       = item.status
            att.note         = item.note
            att.submitted_at = submitted_at
            att.is_late_entry = is_late
        else:
            att = Attendance(
                student_id    = item.student_id,
                group_id      = data.group_id,
                teacher_id    = teacher_id,
                date          = data.date,
                status        = item.status,
                note          = item.note,
                submitted_at  = submitted_at,
                is_late_entry = is_late,
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
        "created":       created,
        "xp_awarded":    xp_count,
        "date":          data.date.isoformat(),
        "group_id":      str(data.group_id),
        "is_late_entry": is_late,
        "submitted_at":  submitted_at.isoformat(),
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


async def get_stats_for_date(
    db: AsyncSession,
    date_val: date,
    branch_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Berilgan kun uchun TO'G'RI davomat statistikasi.

    Denominator: o'sha kuni (hafta kuniga qarab) dars bo'lgan guruhlardagi
                 barcha aktiv o'quvchilar soni (StudentGroup orqali).
    Numerator:   o'sha guruhlarda present/late belgilangan o'quvchilar.

    Agar bitta guruh davomat belgilasa ham, qolgan guruhlar (dars bo'lganlar)
    denominatorda hisoblanadi → to'g'ri foiz ko'rsatiladi.
    """
    from sqlalchemy import case as sa_case

    day_dow = date_val.isoweekday()   # 1=Du ... 7=Ya

    # 1. O'sha kuni dars bo'lgan faol guruhlar
    groups_stmt = select(Group).where(Group.status == "active")
    if branch_id:
        groups_stmt = groups_stmt.where(Group.branch_id == branch_id)
    all_groups = (await db.execute(groups_stmt)).scalars().all()

    groups_with_class = [
        g for g in all_groups
        if any(s.get("day") == day_dow for s in (g.schedule or []))
    ]
    group_ids = [g.id for g in groups_with_class]

    if not group_ids:
        return {
            "expected": 0, "present": 0, "late": 0, "absent": 0,
            "pct": 0.0, "groups_with_class": 0, "groups_marked": 0,
        }

    # 2. Kutilayotgan o'quvchilar — o'sha guruhlardagi DISTINCT aktiv o'quvchilar
    expected = (await db.execute(
        select(func.count(func.distinct(StudentGroup.student_id))).where(
            StudentGroup.group_id.in_(group_ids),
            StudentGroup.is_active == True,
        )
    )).scalar_one() or 0

    if expected == 0:
        return {
            "expected": 0, "present": 0, "late": 0, "absent": 0,
            "pct": 0.0, "groups_with_class": len(group_ids), "groups_marked": 0,
        }

    # 3. Kelgan o'quvchilar — DISTINCT student_id (bir o'quvchi 2 guruhda bo'lsa ham 1 marta)
    #    "Hech bo'lmasa bitta guruhda present/late belgilangan o'quvchi kelgan hisoblanadi"
    present = (await db.execute(
        select(func.count(func.distinct(Attendance.student_id))).where(
            Attendance.date     == date_val,
            Attendance.group_id.in_(group_ids),
            Attendance.status.in_(["present", "late"]),
        )
    )).scalar_one() or 0

    # 4. Nechta guruh davomat kiritgan
    groups_marked = (await db.execute(
        select(func.count(func.distinct(Attendance.group_id))).where(
            Attendance.date     == date_val,
            Attendance.group_id.in_(group_ids),
        )
    )).scalar_one() or 0

    # absent = belgilangan bor, lekin hech qayerda present/late emas
    absent_q = (await db.execute(
        select(func.count(func.distinct(Attendance.student_id))).where(
            Attendance.date     == date_val,
            Attendance.group_id.in_(group_ids),
            Attendance.status   == "absent",
        )
    )).scalar_one() or 0
    # Agar o'quvchi bir guruhda absent, boshqasida present bo'lsa → kelgan hisoblanadi
    absent = max(0, absent_q - present)

    pct = round(min(present / expected * 100, 100.0), 1) if expected > 0 else 0.0

    return {
        "expected":          expected,
        "present":           present,
        "late":              0,       # distinct level da late alohida hisoblanmaydi
        "absent":            absent,
        "pct":               pct,
        "groups_with_class": len(group_ids),
        "groups_marked":     groups_marked,
    }


async def get_group_monthly_pcts(
    db: AsyncSession,
    group_ids: list,
    month: int,
    year: int,
) -> dict:
    """
    Har bir guruh uchun oylik davomat foizini qaytaradi: {group_id_str: pct}.
    Faqat davomat yozuvlari mavjud guruhlar uchun hisobnaydi.
    """
    from sqlalchemy import case as sa_case, extract

    if not group_ids:
        return {}

    rows = (await db.execute(
        select(
            Attendance.group_id,
            func.count(Attendance.id).label("total"),
            func.count(sa_case((Attendance.status.in_(["present", "late"]), 1))).label("present"),
        ).where(
            Attendance.group_id.in_(group_ids),
            extract("month", Attendance.date) == month,
            extract("year",  Attendance.date) == year,
        ).group_by(Attendance.group_id)
    )).all()

    return {
        str(row.group_id): round(row.present / row.total * 100, 1) if row.total else 0.0
        for row in rows
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
    ))
    student.parent_notified = True

