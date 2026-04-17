"""
app/services/group.py

Guruhlar CRUD.
Har bir guruhda o'quvchilar soni, o'qituvchi ma'lumotlari qaytariladi.
"""
import uuid
from typing import Optional, List, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GroupNotFound
from app.models.tenant import Group, Student, StudentGroup, Teacher, User
from app.schemas.group import GroupCreate, GroupUpdate


# ─── yordamchi ───────────────────────────────────────────────────────

async def _student_count(db: AsyncSession, group_id: uuid.UUID) -> int:
    stmt = select(func.count(StudentGroup.id)).where(
        and_(StudentGroup.group_id == group_id, StudentGroup.is_active == True)
    )
    return (await db.execute(stmt)).scalar_one()


async def _teacher_dict(db: AsyncSession, teacher_id: uuid.UUID) -> Optional[dict]:
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.id == teacher_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    t, u = row
    return {
        "id": str(t.id),
        "first_name": u.first_name,
        "last_name": u.last_name,
        "subjects": t.subjects,
    }


async def _to_dict(db: AsyncSession, group: Group) -> dict:
    count = await _student_count(db, group.id)
    teacher = await _teacher_dict(db, group.teacher_id) if group.teacher_id else None
    return {
        "id": str(group.id),
        "name": group.name,
        "subject": group.subject,
        "level": group.level,
        "schedule": group.schedule,
        "monthly_fee": float(group.monthly_fee) if group.monthly_fee else None,
        "max_students": group.max_students,
        "status": group.status,
        "student_count": count,
        "teacher": teacher,
        "teacher_id": str(group.teacher_id) if group.teacher_id else None,
        "branch_id": str(group.branch_id) if group.branch_id else None,
        "start_date": group.start_date.isoformat() if group.start_date else None,
        "end_date": group.end_date.isoformat() if group.end_date else None,
        "created_at": group.created_at.isoformat(),
    }


# ─── asosiy funksiyalar ───────────────────────────────────────────────

async def get_groups(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    teacher_id: Optional[uuid.UUID] = None,
    branch_id: Optional[uuid.UUID] = None,
) -> Tuple[List[dict], int]:

    stmt = select(Group)

    if status:
        stmt = stmt.where(Group.status == status)
    if teacher_id:
        stmt = stmt.where(Group.teacher_id == teacher_id)
    if branch_id:
        stmt = stmt.where(Group.branch_id == branch_id)
    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            or_(Group.name.ilike(q), Group.subject.ilike(q))
        )

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    stmt = stmt.order_by(Group.name).offset((page - 1) * per_page).limit(per_page)
    groups = (await db.execute(stmt)).scalars().all()

    return [await _to_dict(db, g) for g in groups], total


async def get_by_id(db: AsyncSession, group_id: uuid.UUID) -> dict:
    stmt = select(Group).where(Group.id == group_id)
    group = (await db.execute(stmt)).scalar_one_or_none()
    if not group:
        raise GroupNotFound()
    return await _to_dict(db, group)


async def create(db: AsyncSession, data: GroupCreate) -> dict:
    group = Group(
        name=data.name,
        subject=data.subject,
        branch_id=data.branch_id,
        teacher_id=data.teacher_id,
        level=data.level,
        schedule=[s.model_dump() for s in data.schedule] if data.schedule else None,
        start_date=data.start_date,
        end_date=data.end_date,
        monthly_fee=data.monthly_fee,
        max_students=data.max_students,
        status=data.status,
    )
    db.add(group)
    await db.commit()
    return await get_by_id(db, group.id)


async def update(
    db: AsyncSession,
    group_id: uuid.UUID,
    data: GroupUpdate,
) -> dict:
    stmt = select(Group).where(Group.id == group_id)
    group = (await db.execute(stmt)).scalar_one_or_none()
    if not group:
        raise GroupNotFound()

    if data.name         is not None: group.name         = data.name
    if data.subject      is not None: group.subject      = data.subject
    if data.teacher_id   is not None: group.teacher_id   = data.teacher_id
    if data.level        is not None: group.level        = data.level
    if data.monthly_fee  is not None: group.monthly_fee  = data.monthly_fee
    if data.max_students is not None: group.max_students = data.max_students
    if data.status       is not None: group.status       = data.status
    if data.schedule     is not None:
        group.schedule = [s.model_dump() for s in data.schedule]

    await db.commit()
    return await get_by_id(db, group_id)


async def delete(db: AsyncSession, group_id: uuid.UUID) -> None:
    """Guruhni 'completed' holatiga o'tkazish (soft delete)."""
    stmt = select(Group).where(Group.id == group_id)
    group = (await db.execute(stmt)).scalar_one_or_none()
    if not group:
        raise GroupNotFound()
    group.status = "completed"
    await db.commit()


async def get_students(db: AsyncSession, group_id: uuid.UUID) -> List[dict]:
    """Guruh o'quvchilari ro'yxati."""
    stmt = (
        select(Student, User, StudentGroup)
        .join(StudentGroup, StudentGroup.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(
            and_(
                StudentGroup.group_id == group_id,
                StudentGroup.is_active == True,
            )
        )
        .order_by(User.first_name)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": str(s.id),
            "user_id": str(s.user_id),
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": u.phone,
            "balance": float(s.balance),
            "is_active": s.is_active,
            "joined_at": sg.joined_at.isoformat() if sg.joined_at else None,
        }
        for s, u, sg in rows
    ]
