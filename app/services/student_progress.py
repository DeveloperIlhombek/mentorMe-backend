"""
app/services/student_progress.py
O'quvchi o'zlashtirish darajasini boshqarish.

Asosiy logika:
  - Admin yoki teacher o'quvchi uchun progress_dates (JSONB) ni belgilaydi.
  - Har oy boshida (yoki rejalashtirilgan kunda) pending yozuvlar yaratiladi.
  - Teacher scheduled_date kelganda score kiritadi.
  - Kiritilgandan so'ng Telegram orqali o'quvchi va ota-onaga xabar yuboriladi.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import and_, extract, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.progress import StudentProgress
from app.models.tenant.student import Student
from app.models.tenant.group import Group
from app.models.tenant.student import StudentGroup


# ─── Har oy uchun pending yozuvlar yaratish ────────────────────────────

async def generate_monthly_schedules(
    db: AsyncSession,
    month: int,
    year: int,
    student_id: Optional[uuid.UUID] = None,
) -> List[dict]:
    """
    Berilgan oy uchun progress_dates bo'lgan barcha o'quvchilarga
    pending StudentProgress yozuvi yaratadi (agar hali mavjud bo'lmasa).
    Odatda oy boshida cron job tomonidan chaqiriladi.
    """
    stmt = select(Student).where(
        Student.is_active == True,
        func.jsonb_array_length(Student.progress_dates) > 0,
    )
    if student_id:
        stmt = stmt.where(Student.id == student_id)

    students = (await db.execute(stmt)).scalars().all()
    created = []

    for student in students:
        dates = student.progress_dates or []  # e.g. [15, 28]
        for day in dates:
            try:
                sched = date(year, month, int(day))
            except ValueError:
                # Oy qisqaroq bo'lsa (masalan, 30-fevral) — oxirgi kun
                import calendar
                last = calendar.monthrange(year, month)[1]
                sched = date(year, month, min(int(day), last))

            # Mavjudligini tekshirish
            exists = (await db.execute(
                select(StudentProgress).where(
                    StudentProgress.student_id    == student.id,
                    StudentProgress.scheduled_date == sched,
                )
            )).scalar_one_or_none()
            if exists:
                continue

            # O'qituvchini topish (aktiv guruh orqali)
            sg = (await db.execute(
                select(StudentGroup).where(
                    StudentGroup.student_id == student.id,
                    StudentGroup.is_active  == True,
                )
            )).scalars().first()
            teacher_id = None
            group_id   = None
            if sg:
                group_id = sg.group_id
                grp = (await db.execute(
                    select(Group).where(Group.id == sg.group_id)
                )).scalar_one_or_none()
                if grp:
                    teacher_id = grp.teacher_id

            rec = StudentProgress(
                student_id     = student.id,
                group_id       = group_id,
                teacher_id     = teacher_id,
                period_month   = month,
                period_year    = year,
                scheduled_date = sched,
                status         = "pending",
            )
            db.add(rec)
            created.append({
                "student_id": str(student.id),
                "date": str(sched),
            })

    await db.commit()
    return created


# ─── Score kiritish (teacher) ──────────────────────────────────────────

async def submit_progress(
    db: AsyncSession,
    progress_id: uuid.UUID,
    score: float,
    notes: Optional[str],
    submitted_by: uuid.UUID,
) -> dict:
    """O'qituvchi score kiritadi."""
    rec = (await db.execute(
        select(StudentProgress).where(StudentProgress.id == progress_id)
    )).scalar_one_or_none()
    if not rec:
        raise ValueError("Progress yozuvi topilmadi")

    rec.score        = score
    rec.notes        = notes
    rec.status       = "entered"
    rec.submitted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rec)
    return _progress_dict(rec)


# ─── Ko'rish ───────────────────────────────────────────────────────────

async def get_progress(
    db: AsyncSession,
    student_id: Optional[uuid.UUID]  = None,
    teacher_id: Optional[uuid.UUID]  = None,
    month: Optional[int]             = None,
    year:  Optional[int]             = None,
    status: Optional[str]            = None,
) -> List[dict]:
    stmt = select(StudentProgress).order_by(
        StudentProgress.scheduled_date.desc()
    )
    if student_id: stmt = stmt.where(StudentProgress.student_id  == student_id)
    if teacher_id: stmt = stmt.where(StudentProgress.teacher_id  == teacher_id)
    if month:      stmt = stmt.where(StudentProgress.period_month == month)
    if year:       stmt = stmt.where(StudentProgress.period_year  == year)
    if status:     stmt = stmt.where(StudentProgress.status       == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [_progress_dict(r) for r in rows]


async def get_student_progress_summary(
    db: AsyncSession,
    student_id: uuid.UUID,
    month: int,
    year: int,
) -> dict:
    """Bir o'quvchining bir oy bo'yicha qisqa xulosasi."""
    rows = (await db.execute(
        select(StudentProgress).where(
            StudentProgress.student_id  == student_id,
            StudentProgress.period_month == month,
            StudentProgress.period_year  == year,
        ).order_by(StudentProgress.scheduled_date)
    )).scalars().all()

    entered = [r for r in rows if r.status == "entered"]
    avg_score = (
        round(sum(r.score for r in entered) / len(entered), 1)
        if entered else None
    )
    return {
        "student_id":   str(student_id),
        "period":       f"{month}/{year}",
        "total":        len(rows),
        "entered":      len(entered),
        "pending":      sum(1 for r in rows if r.status == "pending"),
        "missed":       sum(1 for r in rows if r.status == "missed"),
        "avg_score":    avg_score,
        "color":        _score_color(avg_score),
        "entries":      [_progress_dict(r) for r in rows],
    }


# ─── Progress kunlarini yangilash (admin/teacher) ──────────────────────

async def set_student_progress_dates(
    db: AsyncSession,
    student_id: uuid.UUID,
    dates: List[int],     # e.g. [15, 28]
) -> dict:
    """O'quvchi uchun progress_dates ni yangilaydi."""
    student = (await db.execute(
        select(Student).where(Student.id == student_id)
    )).scalar_one_or_none()
    if not student:
        raise ValueError("O'quvchi topilmadi")
    student.progress_dates = dates
    await db.commit()
    return {"student_id": str(student_id), "progress_dates": dates}


# ─── Helpers ──────────────────────────────────────────────────────────

def _progress_dict(r: StudentProgress) -> dict:
    return {
        "id":             str(r.id),
        "student_id":     str(r.student_id),
        "group_id":       str(r.group_id)    if r.group_id    else None,
        "teacher_id":     str(r.teacher_id)  if r.teacher_id  else None,
        "period_month":   r.period_month,
        "period_year":    r.period_year,
        "scheduled_date": str(r.scheduled_date),
        "score":          float(r.score) if r.score is not None else None,
        "status":         r.status,
        "color":          _score_color(float(r.score) if r.score is not None else None),
        "notes":          r.notes,
        "notified":       r.notified,
        "submitted_at":   r.submitted_at.isoformat() if r.submitted_at else None,
    }


def _score_color(score: Optional[float]) -> str:
    """Score bo'yicha rang: yashil ≥ 75, sariq 50–74, qizil < 50."""
    if score is None:
        return "gray"
    if score >= 75:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"
