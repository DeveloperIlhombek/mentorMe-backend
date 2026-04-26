"""
app/services/student_progress.py
O'quvchi oylik baholash tizimi.

Logika:
  - Admin guruh uchun deadline_day + deadline_hour belgilaydi.
  - O'qituvchi har oy deadline gacha barcha o'quvchilari uchun 0-100% score kiritadi.
  - Deadline o'tgach kiritilsa → is_late=True → KPI jarima.
  - Vaqtida kiritilsa → KPI bonus.
  - O'quvchi va ota-ona o'z natijalarini ko'ra oladi.
"""
import uuid
import calendar
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import and_, extract, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.progress import StudentProgress
from app.models.tenant.student import Student, StudentGroup
from app.models.tenant.group import Group
from app.models.tenant.user import User


# ─── Teacher: guruh o'quvchilari baholash holati ──────────────────────

async def get_group_assessment(
    db: AsyncSession,
    group_id: uuid.UUID,
    month: int,
    year: int,
) -> dict:
    """
    Guruhning barcha o'quvchilari uchun baholash holati.
    Har bir o'quvchi uchun: mavjud score yoki None.
    """
    group = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not group:
        raise ValueError("Guruh topilmadi")

    # Guruh o'quvchilari
    rows = (await db.execute(
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .join(StudentGroup, StudentGroup.student_id == Student.id)
        .where(
            StudentGroup.group_id  == group_id,
            StudentGroup.is_active == True,
            Student.is_active      == True,
        )
        .order_by(User.first_name)
    )).all()

    # Mavjud yozuvlar
    existing = (await db.execute(
        select(StudentProgress).where(
            StudentProgress.group_id     == group_id,
            StudentProgress.period_month == month,
            StudentProgress.period_year  == year,
        )
    )).scalars().all()
    existing_map = {str(r.student_id): r for r in existing}

    # Deadline hisoblash
    deadline = _calc_deadline(year, month, group.progress_deadline_day, group.progress_deadline_hour)
    now = datetime.utcnow()
    is_overdue = now > deadline
    submitted_count = len([r for r in existing if r.status == "entered"])

    students_data = []
    for student, user in rows:
        rec = existing_map.get(str(student.id))
        students_data.append({
            "student_id":  str(student.id),
            "first_name":  user.first_name,
            "last_name":   user.last_name or "",
            "phone":       user.phone,
            "score":       float(rec.score) if rec and rec.score is not None else None,
            "notes":       rec.notes if rec else None,
            "status":      rec.status if rec else "pending",
            "is_late":     rec.is_late if rec else False,
            "submitted_at":rec.submitted_at.isoformat() if rec and rec.submitted_at else None,
            "record_id":   str(rec.id) if rec else None,
        })

    return {
        "group_id":        str(group_id),
        "group_name":      group.name,
        "period_month":    month,
        "period_year":     year,
        "deadline":        deadline.isoformat(),
        "deadline_day":    group.progress_deadline_day,
        "deadline_hour":   group.progress_deadline_hour,
        "is_overdue":      is_overdue,
        "total_students":  len(students_data),
        "submitted_count": submitted_count,
        "students":        students_data,
    }


# ─── Teacher: bulk kiritish ────────────────────────────────────────────

async def bulk_submit_assessment(
    db: AsyncSession,
    group_id: uuid.UUID,
    month: int,
    year: int,
    teacher_id: uuid.UUID,  # teachers.id (PK)
    scores: List[dict],     # [{student_id, score, notes?}]
) -> dict:
    """
    Guruh uchun barcha o'quvchilar baholashini bir vaqtda saqlash.
    scores = [{"student_id": "...", "score": 85.0, "notes": "..."}]
    """
    group = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not group:
        raise ValueError("Guruh topilmadi")

    now      = datetime.utcnow()
    deadline = _calc_deadline(year, month, group.progress_deadline_day, group.progress_deadline_hour)
    is_late  = now > deadline

    saved = []
    for entry in scores:
        sid   = uuid.UUID(str(entry["student_id"]))
        score = float(entry.get("score") or 0)
        notes = entry.get("notes")

        # Upsert
        rec = (await db.execute(
            select(StudentProgress).where(
                StudentProgress.student_id   == sid,
                StudentProgress.group_id     == group_id,
                StudentProgress.period_month == month,
                StudentProgress.period_year  == year,
            )
        )).scalar_one_or_none()

        if rec:
            rec.score        = score
            rec.notes        = notes
            rec.status       = "entered"
            rec.submitted_at = now
            rec.is_late      = is_late
            rec.teacher_id   = teacher_id
        else:
            rec = StudentProgress(
                student_id     = sid,
                group_id       = group_id,
                teacher_id     = teacher_id,
                period_month   = month,
                period_year    = year,
                scheduled_date = date(year, month, min(group.progress_deadline_day,
                                     calendar.monthrange(year, month)[1])),
                score          = score,
                notes          = notes,
                status         = "entered",
                submitted_at   = now,
                is_late        = is_late,
            )
            db.add(rec)

        await db.flush()
        saved.append({
            "student_id": str(sid),
            "score":      score,
            "is_late":    is_late,
        })

    await db.commit()
    return {
        "group_id":       str(group_id),
        "period":         f"{month}/{year}",
        "saved":          len(saved),
        "is_late":        is_late,
        "deadline":       deadline.isoformat(),
        "entries":        saved,
    }


# ─── Admin: guruh deadline sozlamasi ─────────────────────────────────

async def set_group_deadline(
    db: AsyncSession,
    group_id: uuid.UUID,
    deadline_day:  int,
    deadline_hour: int,
) -> dict:
    """Admin guruh uchun baholash deadline ni belgilaydi."""
    group = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not group:
        raise ValueError("Guruh topilmadi")
    group.progress_deadline_day  = max(1, min(deadline_day, 28))
    group.progress_deadline_hour = max(0, min(deadline_hour, 23))
    await db.commit()
    return {
        "group_id":      str(group_id),
        "deadline_day":  group.progress_deadline_day,
        "deadline_hour": group.progress_deadline_hour,
    }


# ─── Admin/Inspector: o'qituvchi baholashlari ────────────────────────

async def get_teacher_assessments(
    db: AsyncSession,
    teacher_id: uuid.UUID,   # teachers.id
    month: Optional[int] = None,
    year:  Optional[int] = None,
) -> dict:
    """
    Admin uchun: o'qituvchining baholashlari va KPI holati.
    Har guruh uchun: topshirilgan/jami, kechikkan, o'rtacha ball.
    """
    from app.models.tenant.teacher import Teacher
    # Guruhlar
    grp_rows = (await db.execute(
        select(Group).where(Group.teacher_id == teacher_id, Group.status == "active")
    )).scalars().all()

    if not month or not year:
        today = date.today()
        month = month or today.month
        year  = year  or today.year

    result = []
    for g in grp_rows:
        # Bu guruhning o'quvchilari soni
        total_students = (await db.execute(
            select(func.count(StudentGroup.id)).where(
                StudentGroup.group_id  == g.id,
                StudentGroup.is_active == True,
            )
        )).scalar_one()

        # Kiritilgan yozuvlar
        records = (await db.execute(
            select(StudentProgress).where(
                StudentProgress.group_id     == g.id,
                StudentProgress.period_month == month,
                StudentProgress.period_year  == year,
            )
        )).scalars().all()

        submitted   = [r for r in records if r.status == "entered"]
        late_count  = sum(1 for r in submitted if r.is_late)
        avg_score   = (round(sum(float(r.score) for r in submitted if r.score is not None)
                        / len(submitted), 1) if submitted else None)

        deadline = _calc_deadline(year, month, g.progress_deadline_day, g.progress_deadline_hour)
        now      = datetime.utcnow()

        result.append({
            "group_id":       str(g.id),
            "group_name":     g.name,
            "subject":        g.subject,
            "total_students": total_students,
            "submitted":      len(submitted),
            "missing":        total_students - len(submitted),
            "late_count":     late_count,
            "on_time_count":  len(submitted) - late_count,
            "avg_score":      avg_score,
            "deadline":       deadline.isoformat(),
            "deadline_day":   g.progress_deadline_day,
            "deadline_hour":  g.progress_deadline_hour,
            "is_overdue":     now > deadline,
            "completion_pct": round(len(submitted) / total_students * 100)
                              if total_students else 0,
        })

    return {
        "teacher_id": str(teacher_id),
        "period":     f"{month}/{year}",
        "month":      month,
        "year":       year,
        "groups":     result,
        "total_submitted":  sum(g["submitted"]  for g in result),
        "total_students":   sum(g["total_students"] for g in result),
        "total_late":       sum(g["late_count"] for g in result),
    }


# ─── O'quvchi o'z balini ko'rish ─────────────────────────────────────

async def get_student_scores(
    db: AsyncSession,
    student_id: uuid.UUID,
    month: Optional[int] = None,
    year:  Optional[int] = None,
) -> List[dict]:
    """O'quvchi o'zining baholash natijalarini ko'rish."""
    stmt = select(StudentProgress, Group).outerjoin(
        Group, StudentProgress.group_id == Group.id
    ).where(
        StudentProgress.student_id == student_id,
        StudentProgress.status     == "entered",
    ).order_by(StudentProgress.period_year.desc(), StudentProgress.period_month.desc())

    if month: stmt = stmt.where(StudentProgress.period_month == month)
    if year:  stmt = stmt.where(StudentProgress.period_year  == year)

    rows = (await db.execute(stmt)).all()
    return [{
        "id":           str(r.id),
        "group_name":   g.name if g else None,
        "subject":      g.subject if g else None,
        "period_month": r.period_month,
        "period_year":  r.period_year,
        "score":        float(r.score) if r.score is not None else None,
        "color":        _score_color(float(r.score) if r.score else None),
        "notes":        r.notes,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
    } for r, g in rows]


# ─── Admin: barcha o'qituvchilar baholash holati ─────────────────────

async def get_all_teachers_assessment_status(
    db: AsyncSession,
    month: int,
    year:  int,
) -> List[dict]:
    """Admin uchun: barcha o'qituvchilar baholash holati."""
    from app.models.tenant.teacher import Teacher

    teachers = (await db.execute(
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(User.is_active == True)
    )).all()

    result = []
    now = datetime.utcnow()
    for t, u in teachers:
        data = await get_teacher_assessments(db, t.id, month, year)
        if not data["groups"]:
            continue
        result.append({
            "teacher_id":      str(t.id),
            "teacher_name":    f"{u.first_name} {u.last_name or ''}".strip(),
            "phone":           u.phone,
            "total_submitted": data["total_submitted"],
            "total_students":  data["total_students"],
            "total_late":      data["total_late"],
            "completion_pct":  round(data["total_submitted"] / data["total_students"] * 100)
                               if data["total_students"] else 0,
            "groups":          data["groups"],
        })

    return sorted(result, key=lambda x: x["completion_pct"], reverse=True)


# ─── Yordamchilar ─────────────────────────────────────────────────────

def _calc_deadline(year: int, month: int, day: int, hour: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    safe_day = min(day, last_day)
    return datetime(year, month, safe_day, hour, 59, 59)


def _score_color(score: Optional[float]) -> str:
    if score is None: return "gray"
    if score >= 75:   return "green"
    if score >= 50:   return "yellow"
    return "red"


# ─── Legacy: generate_monthly_schedules (backward compat) ────────────

async def generate_monthly_schedules(db, month, year, student_id=None):
    """Eski endpoint uchun saqlangan — yangi tizimda ishlatilmaydi."""
    return []


async def submit_progress(db, progress_id, score, notes, submitted_by):
    """Eski bitta yozuv kiritish — yangi bulk endpoint ishlatiladi."""
    rec = (await db.execute(
        select(StudentProgress).where(StudentProgress.id == progress_id)
    )).scalar_one_or_none()
    if not rec:
        raise ValueError("Topilmadi")
    now = datetime.utcnow()
    rec.score = score; rec.notes = notes
    rec.status = "entered"; rec.submitted_at = now
    await db.commit()
    return {"id": str(rec.id), "score": score, "status": "entered"}


async def get_progress(db, student_id=None, teacher_id=None, month=None, year=None, status=None):
    stmt = select(StudentProgress).order_by(StudentProgress.period_year.desc(),
                                             StudentProgress.period_month.desc())
    if student_id: stmt = stmt.where(StudentProgress.student_id  == student_id)
    if teacher_id: stmt = stmt.where(StudentProgress.teacher_id  == teacher_id)
    if month:      stmt = stmt.where(StudentProgress.period_month == month)
    if year:       stmt = stmt.where(StudentProgress.period_year  == year)
    if status:     stmt = stmt.where(StudentProgress.status       == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": str(r.id), "student_id": str(r.student_id),
             "score": float(r.score) if r.score else None,
             "status": r.status, "is_late": r.is_late,
             "period_month": r.period_month, "period_year": r.period_year,
             "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None}
            for r in rows]


async def get_student_progress_summary(db, student_id, month, year):
    scores = await get_student_scores(db, student_id, month, year)
    avg = round(sum(s["score"] for s in scores if s["score"] is not None) / len(scores), 1) if scores else None
    return {"student_id": str(student_id), "period": f"{month}/{year}",
            "avg_score": avg, "color": _score_color(avg), "entries": scores}
