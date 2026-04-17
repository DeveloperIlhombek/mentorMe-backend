"""app/services/syllabus.py — O'quv yo'li biznes logikasi."""
import uuid
from typing import List, Optional
from datetime import datetime

from sqlalchemy import and_, func, select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.syllabus import (
    Syllabus, SyllabusTopic, SyllabusAssignment, SyllabusProgress
)
from app.models.tenant.student import Student, StudentGroup
from app.models.tenant.user import User


# ── CRUD: Syllabus ────────────────────────────────────────────────────

async def list_syllabuses(
    db: AsyncSession,
    teacher_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> List[dict]:
    stmt = select(Syllabus)
    if teacher_id:
        stmt = stmt.where(Syllabus.created_by == teacher_id)
    if status:
        stmt = stmt.where(Syllabus.status == status)
    stmt = stmt.order_by(Syllabus.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()

    result = []
    for s in rows:
        topics = await list_topics(db, s.id)
        result.append({
            "id":          str(s.id),
            "title":       s.title,
            "description": s.description,
            "subject":     s.subject,
            "status":      s.status,
            "xp_per_topic":s.xp_per_topic,
            "color":       s.color,
            "icon":        s.icon,
            "topic_count": len(topics),
            "created_at":  s.created_at.isoformat() if s.created_at else None,
        })
    return result


async def get_syllabus(db: AsyncSession, syllabus_id: uuid.UUID) -> Optional[dict]:
    s = (await db.execute(
        select(Syllabus).where(Syllabus.id == syllabus_id)
    )).scalar_one_or_none()
    if not s:
        return None
    topics      = await list_topics(db, syllabus_id)
    assignments = await list_assignments(db, syllabus_id)
    return {
        "id":          str(s.id),
        "title":       s.title,
        "description": s.description,
        "subject":     s.subject,
        "status":      s.status,
        "xp_per_topic":s.xp_per_topic,
        "color":       s.color,
        "icon":        s.icon,
        "topics":      topics,
        "assignments": assignments,
        "created_at":  s.created_at.isoformat() if s.created_at else None,
    }


async def create_syllabus(
    db: AsyncSession,
    title: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
    subject: Optional[str] = None,
    xp_per_topic: int = 50,
    color: str = "#4f8ef7",
    icon: str = "📚",
) -> dict:
    s = Syllabus(
        title=title, description=description, subject=subject,
        created_by=created_by, xp_per_topic=xp_per_topic,
        color=color, icon=icon, status="active",
    )
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return await get_syllabus(db, s.id)


async def update_syllabus(
    db: AsyncSession,
    syllabus_id: uuid.UUID,
    **kwargs,
) -> Optional[dict]:
    s = (await db.execute(
        select(Syllabus).where(Syllabus.id == syllabus_id)
    )).scalar_one_or_none()
    if not s:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(s, k):
            setattr(s, k, v)
    s.updated_at = datetime.utcnow()
    await db.flush()
    return await get_syllabus(db, syllabus_id)


async def delete_syllabus(db: AsyncSession, syllabus_id: uuid.UUID) -> bool:
    s = (await db.execute(
        select(Syllabus).where(Syllabus.id == syllabus_id)
    )).scalar_one_or_none()
    if not s:
        return False
    await db.delete(s)
    await db.flush()
    return True


# ── CRUD: Topics ──────────────────────────────────────────────────────

async def list_topics(db: AsyncSession, syllabus_id: uuid.UUID) -> List[dict]:
    stmt = (
        select(SyllabusTopic)
        .where(SyllabusTopic.syllabus_id == syllabus_id, SyllabusTopic.is_active == True)
        .order_by(SyllabusTopic.order_index)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_topic_dict(t) for t in rows]


def _topic_dict(t: SyllabusTopic) -> dict:
    return {
        "id":          str(t.id),
        "syllabus_id": str(t.syllabus_id),
        "title":       t.title,
        "description": t.description,
        "order_index": t.order_index,
        "xp_reward":   t.xp_reward,
    }


async def add_topic(
    db: AsyncSession,
    syllabus_id: uuid.UUID,
    title: str,
    description: Optional[str] = None,
    order_index: Optional[int] = None,
    xp_reward: int = 50,
) -> dict:
    if order_index is None:
        max_idx = (await db.execute(
            select(func.max(SyllabusTopic.order_index))
            .where(SyllabusTopic.syllabus_id == syllabus_id)
        )).scalar_one() or 0
        order_index = max_idx + 1

    t = SyllabusTopic(
        syllabus_id=syllabus_id, title=title,
        description=description, order_index=order_index,
        xp_reward=xp_reward,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return _topic_dict(t)


async def update_topic(
    db: AsyncSession, topic_id: uuid.UUID, **kwargs
) -> Optional[dict]:
    t = (await db.execute(
        select(SyllabusTopic).where(SyllabusTopic.id == topic_id)
    )).scalar_one_or_none()
    if not t:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(t, k):
            setattr(t, k, v)
    await db.flush()
    return _topic_dict(t)


async def delete_topic(db: AsyncSession, topic_id: uuid.UUID) -> bool:
    t = (await db.execute(
        select(SyllabusTopic).where(SyllabusTopic.id == topic_id)
    )).scalar_one_or_none()
    if not t:
        return False
    t.is_active = False
    await db.flush()
    return True


async def reorder_topics(
    db: AsyncSession,
    syllabus_id: uuid.UUID,
    topic_ids: List[uuid.UUID],
) -> List[dict]:
    """Mavzularni qayta tartiblash."""
    for idx, tid in enumerate(topic_ids):
        t = (await db.execute(
            select(SyllabusTopic).where(SyllabusTopic.id == tid)
        )).scalar_one_or_none()
        if t and t.syllabus_id == syllabus_id:
            t.order_index = idx
    await db.flush()
    return await list_topics(db, syllabus_id)


# ── Assignments ───────────────────────────────────────────────────────

async def list_assignments(db: AsyncSession, syllabus_id: uuid.UUID) -> List[dict]:
    rows = (await db.execute(
        select(SyllabusAssignment).where(SyllabusAssignment.syllabus_id == syllabus_id)
    )).scalars().all()
    return [{
        "id":          str(a.id),
        "target_type": a.target_type,
        "target_id":   str(a.target_id),
        "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
    } for a in rows]


async def assign_syllabus(
    db: AsyncSession,
    syllabus_id: uuid.UUID,
    target_type: str,   # group | student
    target_id: uuid.UUID,
    assigned_by: uuid.UUID,
) -> dict:
    # Mavjud assignment tekshirish
    existing = (await db.execute(
        select(SyllabusAssignment).where(
            SyllabusAssignment.syllabus_id == syllabus_id,
            SyllabusAssignment.target_type == target_type,
            SyllabusAssignment.target_id   == target_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"id": str(existing.id), "already_exists": True}

    a = SyllabusAssignment(
        syllabus_id=syllabus_id,
        target_type=target_type,
        target_id=target_id,
        assigned_by=assigned_by,
    )
    db.add(a)
    await db.flush()
    return {"id": str(a.id), "assigned": True}


async def unassign_syllabus(
    db: AsyncSession,
    syllabus_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        sql_delete(SyllabusAssignment).where(
            SyllabusAssignment.syllabus_id == syllabus_id,
            SyllabusAssignment.target_type == target_type,
            SyllabusAssignment.target_id   == target_id,
        )
    )
    await db.flush()
    return result.rowcount > 0


# ── Progress ──────────────────────────────────────────────────────────

async def get_student_syllabuses(
    db: AsyncSession,
    student_id: uuid.UUID,
) -> List[dict]:
    """O'quvchiga biriktirilgan barcha syllabuslar + progress."""
    # Guruh orqali biriktirilganlar
    groups_stmt = (
        select(StudentGroup.group_id)
        .where(StudentGroup.student_id == student_id, StudentGroup.is_active == True)
    )
    group_ids = [r[0] for r in (await db.execute(groups_stmt)).all()]

    # Barcha assignment lar (guruh + individual)
    assignment_filters = [
        and_(SyllabusAssignment.target_type == "student",
             SyllabusAssignment.target_id   == student_id),
    ]
    if group_ids:
        assignment_filters.append(
            and_(SyllabusAssignment.target_type == "group",
                 SyllabusAssignment.target_id.in_(group_ids))
        )

    from sqlalchemy import or_
    assignments = (await db.execute(
        select(SyllabusAssignment.syllabus_id).where(or_(*assignment_filters))
    )).scalars().all()

    syllabus_ids = list(set(assignments))
    if not syllabus_ids:
        return []

    result = []
    for sid in syllabus_ids:
        s = (await db.execute(
            select(Syllabus).where(Syllabus.id == sid, Syllabus.status == "active")
        )).scalar_one_or_none()
        if not s:
            continue

        topics = await list_topics(db, sid)
        completed_ids = set(
            str(r[0]) for r in (await db.execute(
                select(SyllabusProgress.topic_id).where(
                    SyllabusProgress.student_id == student_id,
                    SyllabusProgress.topic_id.in_([uuid.UUID(t["id"]) for t in topics])
                )
            )).all()
        )

        # Ketma-ket: birinchi tugallanmagan = joriy
        enriched_topics = []
        current_found = False
        for t in topics:
            done   = t["id"] in completed_ids
            is_cur = not done and not current_found
            if is_cur:
                current_found = True
            enriched_topics.append({
                **t,
                "completed": done,
                "is_current": is_cur,
                "locked": not done and not is_cur,
            })

        completed_count = len(completed_ids)
        result.append({
            "id":              str(s.id),
            "title":           s.title,
            "subject":         s.subject,
            "color":           s.color,
            "icon":            s.icon,
            "topics":          enriched_topics,
            "total_topics":    len(topics),
            "completed_topics":completed_count,
            "progress_pct":    round(completed_count / len(topics) * 100) if topics else 0,
            "total_xp":        sum(t["xp_reward"] for t in topics if t["id"] in completed_ids),
        })

    return result


async def complete_topic(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    topic_id: uuid.UUID,
    student_id: uuid.UUID,
) -> dict:
    """O'qituvchi mavzuni bajarildi deb belgilaydi va XP beradi."""
    # Mavjud mi?
    existing = (await db.execute(
        select(SyllabusProgress).where(
            SyllabusProgress.student_id == student_id,
            SyllabusProgress.topic_id   == topic_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"already_completed": True, "xp_given": existing.xp_given}

    topic = (await db.execute(
        select(SyllabusTopic).where(SyllabusTopic.id == topic_id)
    )).scalar_one_or_none()
    if not topic:
        return {"error": "Topic not found"}

    # Ketma-ket tekshirish: oldingi mavzu bajarilganmi?
    if topic.order_index > 0:
        prev_topic = (await db.execute(
            select(SyllabusTopic).where(
                SyllabusTopic.syllabus_id == topic.syllabus_id,
                SyllabusTopic.order_index == topic.order_index - 1,
                SyllabusTopic.is_active   == True,
            )
        )).scalar_one_or_none()
        if prev_topic:
            prev_done = (await db.execute(
                select(SyllabusProgress).where(
                    SyllabusProgress.student_id == student_id,
                    SyllabusProgress.topic_id   == prev_topic.id,
                )
            )).scalar_one_or_none()
            if not prev_done:
                return {"error": "Previous topic not completed", "blocked": True}

    xp = topic.xp_reward
    progress = SyllabusProgress(
        student_id=student_id,
        topic_id=topic_id,
        completed_by=teacher_id,
        xp_given=xp,
    )
    db.add(progress)
    await db.flush()

    # XP berish
    from app.services.gamification import award_xp
    try:
        await award_xp(
            db, student_id, xp,
            reason="topic_completed",
            reference_id=topic_id,
        )
    except Exception:
        pass

    return {
        "completed": True,
        "topic_id": str(topic_id),
        "xp_given": xp,
        "topic_title": topic.title,
    }


async def bulk_complete_topics(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    topic_id: uuid.UUID,
    student_ids: List[uuid.UUID],
) -> List[dict]:
    """Bir mavzuni bir necha o'quvchi uchun belgilash."""
    results = []
    for sid in student_ids:
        r = await complete_topic(db, teacher_id, topic_id, sid)
        results.append({"student_id": str(sid), **r})
    await db.commit()
    return results


# ── Leaderboard ───────────────────────────────────────────────────────

async def get_leaderboard(
    db: AsyncSession,
    teacher_id: Optional[uuid.UUID] = None,
    group_id: Optional[uuid.UUID] = None,
    period: str = "weekly",   # weekly | alltime
) -> dict:
    """O'qituvchi uchun leaderboard — faqat o'z guruhlari."""
    from app.models.tenant.student import Student
    from app.models.tenant.gamification import GamificationProfile
    from app.models.tenant.attendance import Attendance
    from app.models.tenant.group import Group
    from datetime import date

    today = date.today()

    # O'qituvchining guruhlarini aniqlash
    if group_id:
        # Aniq guruh tanlangan
        stmt = (
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .join(StudentGroup, StudentGroup.student_id == Student.id)
            .where(StudentGroup.group_id == group_id, StudentGroup.is_active == True, Student.is_active == True)
        )
    elif teacher_id:
        # O'qituvchining barcha guruhlari
        teacher_group_ids = [
            r[0] for r in (await db.execute(
                select(Group.id).where(Group.teacher_id == teacher_id, Group.status == "active")
            )).all()
        ]
        if not teacher_group_ids:
            return {"students": [], "podium": [], "groups": []}
        stmt = (
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .join(StudentGroup, StudentGroup.student_id == Student.id)
            .where(
                StudentGroup.group_id.in_(teacher_group_ids),
                StudentGroup.is_active == True,
                Student.is_active == True,
            )
            .distinct(Student.id)
        )
    else:
        stmt = (
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .where(Student.is_active == True)
        )

    students = (await db.execute(stmt)).all()
    if not students:
        return {"students": [], "podium": []}

    entries = []
    for student, user in students:
        # XP
        gp = (await db.execute(
            select(GamificationProfile).where(GamificationProfile.student_id == student.id)
        )).scalar_one_or_none()

        xp = gp.weekly_xp if (gp and period == "weekly") else (gp.total_xp if gp else 0)
        streak = gp.current_streak if gp else 0

        # Davomat (bu oy)
        att_total = (await db.execute(
            select(func.count(Attendance.id)).where(
                Attendance.student_id == student.id,
                Attendance.date >= today.replace(day=1),
            )
        )).scalar_one()
        att_present = (await db.execute(
            select(func.count(Attendance.id)).where(
                Attendance.student_id == student.id,
                Attendance.status.in_(["present", "late"]),
                Attendance.date >= today.replace(day=1),
            )
        )).scalar_one()
        att_pct = round(att_present / att_total * 100) if att_total else 0

        # Syllabus progress (umumiy)
        total_topics = (await db.execute(
            select(func.count(SyllabusProgress.id)).where(
                SyllabusProgress.student_id == student.id
            )
        )).scalar_one()

        entries.append({
            "student_id":   str(student.id),
            "name":         f"{user.first_name} {user.last_name or ''}".strip(),
            "avatar":       (user.first_name or "?")[0].upper(),
            "xp":           xp,
            "streak":       streak,
            "attendance_pct":att_pct,
            "topics_done":  total_topics,
        })

    # XP bo'yicha saralash
    entries.sort(key=lambda e: e["xp"], reverse=True)
    for i, e in enumerate(entries):
        e["rank"] = i + 1

    podium = entries[:3]

    return {
        "period":   period,
        "students": entries,
        "podium":   podium,
        "total":    len(entries),
    }
