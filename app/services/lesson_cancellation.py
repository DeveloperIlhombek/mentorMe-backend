"""
app/services/lesson_cancellation.py
Dars bekor qilish va to'lov korreksiyasi.

Logika:
  - scope='group'   → guruhning barcha aktiv o'quvchilari uchun PaymentAdjustment yaratiladi.
  - scope='student' → faqat tanlangan o'quvchi uchun.
  - adj_type='credit' → payment_day += days_adjusted  (sana uzayadi, o'quvchi foyda ko'radi).
  - adj_type='debit'  → payment_day -= days_adjusted  (sana qisqaradi, qo'shimcha dars).

  Bir darsning kunlik narxi:
    lesson_cost = monthly_fee / lessons_per_month
    days_adjusted = lesson_cost / (monthly_fee / days_in_month) = days_in_month / lessons_per_month
"""
import uuid
import calendar
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.lesson_cancellation import LessonCancellation, PaymentAdjustment
from app.models.tenant.student import Student, StudentGroup
from app.models.tenant.group import Group


# ─── Dars bekor qilish ────────────────────────────────────────────────

async def cancel_lesson(
    db: AsyncSession,
    group_id: uuid.UUID,
    lesson_date: date,
    scope: str = "group",           # 'group' | 'student'
    student_id: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    created_by_role: str = "teacher",  # 'teacher' | 'admin' | 'inspector'
) -> dict:
    """
    Darsni bekor qiladi.
    - Teacher → status='pending', to'lov o'zgartirilmaydi (admin tasdiqlashi kerak)
    - Admin/Inspector → status='approved', to'lov darhol o'zgartiriladi
    """
    if scope == "student" and not student_id:
        raise ValueError("scope='student' uchun student_id kerak")

    group = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not group:
        raise ValueError("Guruh topilmadi")

    is_admin = created_by_role in ("admin", "super_admin", "inspector")
    status = "approved" if is_admin else "pending"

    # LessonCancellation yozuvi
    cancel = LessonCancellation(
        group_id         = group_id,
        scope            = scope,
        student_id       = student_id if scope == "student" else None,
        lesson_date      = lesson_date,
        reason           = reason,
        status           = status,
        payment_adjusted = False,
        created_by       = created_by,
        reviewed_by      = created_by if is_admin else None,
        reviewed_at      = datetime.utcnow() if is_admin else None,
    )
    db.add(cancel)
    await db.flush()  # id olish uchun

    adjustments = []
    if is_admin:
        # Admin/Inspektor — darhol to'lovni o'zgartirish
        if scope == "student":
            target_students = await _get_students([student_id], db)
        else:
            sg_rows = (await db.execute(
                select(StudentGroup.student_id).where(
                    StudentGroup.group_id  == group_id,
                    StudentGroup.is_active == True,
                )
            )).scalars().all()
            target_students = await _get_students(list(sg_rows), db)

        for student in target_students:
            adj = await _create_adjustment(
                db          = db,
                student     = student,
                group       = group,
                cancel_id   = cancel.id,
                adj_type    = "credit",
                lesson_date = lesson_date,
                created_by  = created_by,
            )
            adjustments.append(adj)
        cancel.payment_adjusted = True

    await db.commit()

    return {
        "cancellation_id": str(cancel.id),
        "group_id":        str(group_id),
        "lesson_date":     str(lesson_date),
        "scope":           scope,
        "status":          status,
        "affected_count":  len(adjustments),
        "adjustments":     adjustments,
    }


# ─── Qo'shimcha dars (to'lovni qisqartirish) ─────────────────────────

async def add_extra_lesson(
    db: AsyncSession,
    group_id: uuid.UUID,
    lesson_date: date,
    scope: str = "group",
    student_id: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    created_by_role: str = "teacher",
) -> dict:
    """
    Qo'shimcha (rejalashtirilmagan) dars qo'shadi.
    - Teacher → status='pending', to'lov o'zgartirilmaydi (admin tasdiqlashi kerak)
    - Admin/Inspector → status='approved', to'lov darhol o'zgartiriladi
    """
    if scope == "student" and not student_id:
        raise ValueError("scope='student' uchun student_id kerak")

    group = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not group:
        raise ValueError("Guruh topilmadi")

    is_admin = created_by_role in ("admin", "super_admin", "inspector")
    status = "approved" if is_admin else "pending"

    cancel = LessonCancellation(
        group_id         = group_id,
        scope            = scope,
        student_id       = student_id if scope == "student" else None,
        lesson_date      = lesson_date,
        reason           = f"[extra_lesson] {reason or ''}".strip(),
        status           = status,
        payment_adjusted = False,
        created_by       = created_by,
        reviewed_by      = created_by if is_admin else None,
        reviewed_at      = datetime.utcnow() if is_admin else None,
    )
    db.add(cancel)
    await db.flush()

    adjustments = []
    if is_admin:
        if scope == "student":
            target_students = await _get_students([student_id], db)
        else:
            sg_rows = (await db.execute(
                select(StudentGroup.student_id).where(
                    StudentGroup.group_id  == group_id,
                    StudentGroup.is_active == True,
                )
            )).scalars().all()
            target_students = await _get_students(list(sg_rows), db)

        for student in target_students:
            adj = await _create_adjustment(
                db          = db,
                student     = student,
                group       = group,
                cancel_id   = cancel.id,
                adj_type    = "debit",
                lesson_date = lesson_date,
                created_by  = created_by,
            )
            adjustments.append(adj)
        cancel.payment_adjusted = True

    await db.commit()

    return {
        "cancellation_id": str(cancel.id),
        "group_id":        str(group_id),
        "lesson_date":     str(lesson_date),
        "scope":           scope,
        "status":          status,
        "affected_count":  len(adjustments),
        "adjustments":     adjustments,
    }


# ─── Ko'rish ──────────────────────────────────────────────────────────

async def get_cancellations(
    db: AsyncSession,
    group_id: Optional[uuid.UUID]   = None,
    student_id: Optional[uuid.UUID] = None,
) -> List[dict]:
    stmt = (
        select(LessonCancellation, Group)
        .outerjoin(Group, LessonCancellation.group_id == Group.id)
        .order_by(LessonCancellation.lesson_date.desc())
    )
    if group_id:   stmt = stmt.where(LessonCancellation.group_id   == group_id)
    if student_id: stmt = stmt.where(LessonCancellation.student_id == student_id)
    rows = (await db.execute(stmt)).all()
    result = []
    for lc, g in rows:
        d = _cancel_dict(lc)
        d["group_name"] = g.name if g else None
        result.append(d)
    return result


async def get_adjustments(
    db: AsyncSession,
    student_id: Optional[uuid.UUID] = None,
    group_id: Optional[uuid.UUID]   = None,
) -> List[dict]:
    stmt = select(PaymentAdjustment).order_by(PaymentAdjustment.created_at.desc())
    if student_id: stmt = stmt.where(PaymentAdjustment.student_id == student_id)
    if group_id:   stmt = stmt.where(PaymentAdjustment.group_id   == group_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_adj_dict(r) for r in rows]


# ─── Admin: So'rovni tasdiqlash / rad etish ───────────────────────────

async def approve_cancellation(
    db: AsyncSession,
    cancellation_id: uuid.UUID,
    reviewed_by: Optional[uuid.UUID] = None,
) -> dict:
    """
    Admin/Inspektor dars so'rovini tasdiqlaydi.
    status='approved', payment_day o'zgartiriladi.
    """
    lc = (await db.execute(
        select(LessonCancellation).where(LessonCancellation.id == cancellation_id)
    )).scalar_one_or_none()
    if not lc:
        raise ValueError("So'rov topilmadi")
    if lc.status != "pending":
        raise ValueError(f"So'rov allaqachon '{lc.status}' holatida")

    group = (await db.execute(
        select(Group).where(Group.id == lc.group_id)
    )).scalar_one_or_none()
    if not group:
        raise ValueError("Guruh topilmadi")

    is_extra = lc.reason and lc.reason.startswith("[extra_lesson]")
    adj_type = "debit" if is_extra else "credit"

    # O'quvchilarni aniqlash
    if lc.scope == "student" and lc.student_id:
        target_students = await _get_students([lc.student_id], db)
    else:
        sg_rows = (await db.execute(
            select(StudentGroup.student_id).where(
                StudentGroup.group_id  == lc.group_id,
                StudentGroup.is_active == True,
            )
        )).scalars().all()
        target_students = await _get_students(list(sg_rows), db)

    adjustments = []
    for student in target_students:
        adj = await _create_adjustment(
            db          = db,
            student     = student,
            group       = group,
            cancel_id   = lc.id,
            adj_type    = adj_type,
            lesson_date = lc.lesson_date,
            created_by  = reviewed_by,
        )
        adjustments.append(adj)

    lc.status           = "approved"
    lc.payment_adjusted = True
    lc.reviewed_by      = reviewed_by
    lc.reviewed_at      = datetime.utcnow()
    await db.commit()

    return {
        "cancellation_id": str(lc.id),
        "status":          "approved",
        "affected_count":  len(adjustments),
        "adjustments":     adjustments,
    }


async def reject_cancellation(
    db: AsyncSession,
    cancellation_id: uuid.UUID,
    reviewed_by: Optional[uuid.UUID] = None,
) -> dict:
    """
    Admin/Inspektor dars so'rovini rad etadi.
    status='rejected', payment_day o'zgartirilmaydi.
    """
    lc = (await db.execute(
        select(LessonCancellation).where(LessonCancellation.id == cancellation_id)
    )).scalar_one_or_none()
    if not lc:
        raise ValueError("So'rov topilmadi")
    if lc.status != "pending":
        raise ValueError(f"So'rov allaqachon '{lc.status}' holatida")

    lc.status      = "rejected"
    lc.reviewed_by = reviewed_by
    lc.reviewed_at = datetime.utcnow()
    await db.commit()

    return {"cancellation_id": str(lc.id), "status": "rejected"}


async def list_pending(
    db: AsyncSession,
    group_id: Optional[uuid.UUID] = None,
) -> List[dict]:
    """
    Admin/Inspektor uchun: barcha 'pending' so'rovlar (o'qituvchi + guruh nomi bilan).
    """
    from app.models.tenant import User
    from app.models.tenant.teacher import Teacher

    stmt = (
        select(LessonCancellation, Group, User)
        .outerjoin(Group, LessonCancellation.group_id == Group.id)
        .outerjoin(User, LessonCancellation.created_by == User.id)
        .where(LessonCancellation.status == "pending")
        .order_by(LessonCancellation.created_at.desc())
    )
    if group_id:
        stmt = stmt.where(LessonCancellation.group_id == group_id)

    rows = (await db.execute(stmt)).all()
    result = []
    for lc, g, u in rows:
        d = _cancel_dict(lc)
        d["group_name"]     = g.name if g else None
        d["group_subject"]  = g.subject if g else None
        d["teacher_name"]   = f"{u.first_name} {u.last_name or ''}".strip() if u else None
        d["is_extra"]       = bool(lc.reason and lc.reason.startswith("[extra_lesson]"))
        result.append(d)
    return result


# ─── To'lov korreksiyasi hisoblash ──────────────────────────────────

async def _create_adjustment(
    db: AsyncSession,
    student: Student,
    group: Group,
    cancel_id: uuid.UUID,
    adj_type: str,       # 'credit' | 'debit'
    lesson_date: date,
    created_by: Optional[uuid.UUID],
) -> dict:
    """
    Bir o'quvchi uchun PaymentAdjustment yaratib, payment_day ni yangilaydi.
    """
    monthly_fee = float(student.monthly_fee or group.monthly_fee or 0)
    if monthly_fee == 0:
        return {"student_id": str(student.id), "skipped": True, "reason": "monthly_fee=0"}

    # Oylik darslar sonini hisoblash (guruh schedule dan)
    lessons_per_month = _count_monthly_lessons(group.schedule, lesson_date)
    if lessons_per_month == 0:
        lessons_per_month = 8  # default: haftada 2 ta dars

    days_in_month  = calendar.monthrange(lesson_date.year, lesson_date.month)[1]
    lesson_cost    = round(monthly_fee / lessons_per_month, 2)
    days_adjusted  = round(days_in_month / lessons_per_month, 2)

    # payment_day yangilash
    current_day = student.payment_day or 1
    if adj_type == "credit":
        new_day = min(current_day + round(days_adjusted), days_in_month)
    else:
        new_day = max(current_day - round(days_adjusted), 1)

    student.payment_day = new_day

    rec = PaymentAdjustment(
        student_id      = student.id,
        group_id        = group.id,
        cancellation_id = cancel_id,
        adj_type        = adj_type,
        amount          = lesson_cost,
        days_adjusted   = days_adjusted,
        note            = ("Dars bekor" if adj_type == "credit" else "Qo'shimcha dars") + f": {lesson_date}",
        created_by      = created_by,
    )
    db.add(rec)
    return {
        "student_id":    str(student.id),
        "adj_type":      adj_type,
        "lesson_cost":   lesson_cost,
        "days_adjusted": days_adjusted,
        "old_payment_day": current_day,
        "new_payment_day": new_day,
    }


def _count_monthly_lessons(schedule: list, ref_date: date) -> int:
    """
    Guruh haftalik jadvalidan oylik darslar sonini hisoblaydi.
    schedule = [{day: int (1-7), start: "09:00", end: "10:30", room: "1"}, ...]
    """
    if not schedule:
        return 0
    days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1]
    weeks = days_in_month / 7
    return round(len(schedule) * weeks)


async def _get_students(
    student_ids: List[uuid.UUID], db: AsyncSession
) -> List[Student]:
    if not student_ids:
        return []
    rows = (await db.execute(
        select(Student).where(Student.id.in_(student_ids), Student.is_active == True)
    )).scalars().all()
    return list(rows)


def _cancel_dict(r: LessonCancellation) -> dict:
    return {
        "id":               str(r.id),
        "group_id":         str(r.group_id),
        "scope":            r.scope,
        "student_id":       str(r.student_id) if r.student_id else None,
        "lesson_date":      str(r.lesson_date),
        "reason":           r.reason,
        "status":           r.status,
        "payment_adjusted": r.payment_adjusted,
        "reviewed_by":      str(r.reviewed_by) if r.reviewed_by else None,
        "reviewed_at":      r.reviewed_at.isoformat() if r.reviewed_at else None,
        "created_at":       r.created_at.isoformat(),
    }


def _adj_dict(r: PaymentAdjustment) -> dict:
    return {
        "id":              str(r.id),
        "student_id":      str(r.student_id),
        "group_id":        str(r.group_id)        if r.group_id        else None,
        "cancellation_id": str(r.cancellation_id) if r.cancellation_id else None,
        "adj_type":        r.adj_type,
        "amount":          float(r.amount),
        "days_adjusted":   float(r.days_adjusted),
        "note":            r.note,
        "created_at":      r.created_at.isoformat(),
    }
