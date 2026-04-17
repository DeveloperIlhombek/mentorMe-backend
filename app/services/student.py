"""
app/services/student.py

Student CRUD + guruhlarga biriktirish.

Qoida: service faqat DB bilan ishlaydi.
       HTTP, JWT, request haqida hech narsa bilmaydi.
"""
import uuid
from datetime import date
from typing import Optional, List, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StudentNotFound
from app.core.security import hash_password
from app.models.tenant import (
    GamificationProfile, Group, Student, StudentGroup, User,
)
from app.schemas.student import StudentCreate, StudentUpdate

# Default parol yangi o'quvchi uchun
DEFAULT_STUDENT_PASSWORD = "Student123!"


# ─── yordamchi funksiyalar ────────────────────────────────────────────

async def _get_student_groups(db: AsyncSession, student_id: uuid.UUID) -> list:
    """O'quvchining faol guruhlarini olish."""
    stmt = (
        select(Group, StudentGroup)
        .join(StudentGroup, StudentGroup.group_id == Group.id)
        .where(
            and_(
                StudentGroup.student_id == student_id,
                StudentGroup.is_active == True,
            )
        )
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": str(g.id),
            "name": g.name,
            "subject": g.subject,
            "monthly_fee": float(g.monthly_fee) if g.monthly_fee else None,
            "status": g.status,
        }
        for g, _ in rows
    ]


async def _row_to_dict(db: AsyncSession, student: Student, user: User) -> dict:
    """Student + User -> dict (response uchun)."""
    groups = await _get_student_groups(db, student.id)

    gam_stmt = select(GamificationProfile).where(
        GamificationProfile.student_id == student.id
    )
    gam = (await db.execute(gam_stmt)).scalar_one_or_none()

    return {
        "id": str(student.id),
        "user_id": str(student.user_id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "email": user.email,
        "telegram_id": user.telegram_id,
        "avatar_url": user.avatar_url,
        "language_code": user.language_code,
        "balance": float(student.balance),
        "is_active": student.is_active,
        "is_verified": user.is_verified,
        "enrolled_at": student.enrolled_at.isoformat() if student.enrolled_at else None,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "gender": student.gender,
        "parent_phone": student.parent_phone,
        "notes": student.notes,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "groups": groups,
        "gamification": {
            "total_xp": gam.total_xp,
            "current_level": gam.current_level,
            "current_streak": gam.current_streak,
            "max_streak": gam.max_streak,
            "weekly_xp": gam.weekly_xp,
        } if gam else None,
    }


# ─── asosiy funksiyalar ───────────────────────────────────────────────

async def get_students(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    group_id: Optional[uuid.UUID] = None,
    is_active: Optional[bool] = None,
    branch_id: Optional[uuid.UUID] = None,
) -> Tuple[List[dict], int]:
    """
    O'quvchilar ro'yxati.
    - search: ism, familiya, telefon yoki email bo'yicha
    - group_id: faqat shu guruh o'quvchilari
    - is_active: faol/nofaol filter
    """
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(User.role == "student")
    )

    if is_active is not None:
        stmt = stmt.where(Student.is_active == is_active)

    if branch_id:
        stmt = stmt.where(Student.branch_id == branch_id)

    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.first_name.ilike(q),
                User.last_name.ilike(q),
                User.phone.ilike(q),
                User.email.ilike(q),
            )
        )

    if group_id:
        stmt = stmt.join(
            StudentGroup,
            and_(
                StudentGroup.student_id == Student.id,
                StudentGroup.is_active == True,
                StudentGroup.group_id == group_id,
            ),
        )

    # Jami soni
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Sahifalash
    stmt = (
        stmt
        .order_by(User.first_name)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(stmt)).all()

    result = []
    for student, user in rows:
        groups = await _get_student_groups(db, student.id)
        result.append({
            "id": str(student.id),
            "user_id": str(student.user_id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "email": user.email,
            "balance": float(student.balance),
            "is_active": student.is_active,
            "enrolled_at": student.enrolled_at.isoformat() if student.enrolled_at else None,
            "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
            "gender": student.gender,
            "parent_phone": student.parent_phone,
            "notes": student.notes,
            "groups": groups,
        })

    return result, total


async def get_by_id(db: AsyncSession, student_id: uuid.UUID) -> dict:
    """Bitta o'quvchi to'liq ma'lumoti."""
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.id == student_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise StudentNotFound()
    return await _row_to_dict(db, row[0], row[1])


async def create(
    db:          AsyncSession,
    data:        StudentCreate,
    created_by:  Optional[uuid.UUID] = None,
    role:        str = "admin",          # "admin" | "teacher"
) -> dict:
    """
    Yangi o'quvchi qo'shish.
    Teacher yaratsa is_approved=False → admin tasdiqlamagunicha nofaol.
    """
    is_approved = role == "admin"

    # 1. User — teacher yaratsa is_active=False (admin tasdiqlaganda True bo'ladi)
    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        email=data.email,
        role="student",
        password_hash=hash_password(DEFAULT_STUDENT_PASSWORD),
        telegram_id=getattr(data, 'telegram_id', None),
        telegram_username=getattr(data, 'telegram_username', None),
        is_active=is_approved,
        is_verified=False,
    )
    db.add(user)
    await db.flush()

    # 2. Student
    student = Student(
        user_id=user.id,
        branch_id=data.branch_id,
        date_of_birth=data.date_of_birth,
        gender=data.gender,
        parent_phone=data.parent_phone,
        notes=data.notes,
        payment_day=getattr(data, 'payment_day', 1) or 1,
        monthly_fee=getattr(data, 'monthly_fee', None),
        is_approved=is_approved,
        created_by=created_by,
        balance=0,
        enrolled_at=date.today(),
    )
    db.add(student)
    await db.flush()

    # 3. Guruhga biriktirish
    if data.group_ids:
        for gid in data.group_ids:
            db.add(StudentGroup(student_id=student.id, group_id=gid))

    # 4. Gamification profil
    db.add(GamificationProfile(student_id=student.id))

    await db.commit()
    return await get_by_id(db, student.id)


async def update(
    db: AsyncSession,
    student_id: uuid.UUID,
    data: StudentUpdate,
) -> dict:
    """O'quvchi ma'lumotlarini yangilash."""
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.id == student_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise StudentNotFound()

    student, user = row

    # User maydonlari
    if data.first_name is not None: user.first_name = data.first_name
    if data.last_name  is not None: user.last_name  = data.last_name
    if data.phone      is not None: user.phone      = data.phone
    if data.email      is not None: user.email      = data.email

    # Student maydonlari
    if data.date_of_birth is not None: student.date_of_birth = data.date_of_birth
    if data.gender        is not None: student.gender        = data.gender
    if data.parent_phone  is not None: student.parent_phone  = data.parent_phone
    if data.branch_id     is not None: student.branch_id     = data.branch_id
    if data.notes         is not None: student.notes         = data.notes
    if data.is_active       is not None:
        student.is_active = data.is_active
        user.is_active    = data.is_active
    if getattr(data, 'payment_day', None)      is not None: student.payment_day     = data.payment_day
    if getattr(data, 'monthly_fee', None)      is not None: student.monthly_fee     = data.monthly_fee
    if getattr(data, 'is_approved', None)      is not None:
        student.is_approved = data.is_approved
        if data.is_approved:
            user.is_active = True
            student.is_active = True
    if getattr(data, 'pending_delete', None)   is not None: student.pending_delete  = data.pending_delete
    if getattr(data, 'telegram_id', None)      is not None: user.telegram_id        = data.telegram_id
    if getattr(data, 'telegram_username', None) is not None: user.telegram_username = data.telegram_username

    await db.commit()
    return await get_by_id(db, student_id)


async def soft_delete(db: AsyncSession, student_id: uuid.UUID) -> None:
    """
    Soft delete: is_active = False.
    Ma'lumotlar o'chirilmaydi, faqat ko'rsatilmaydi.
    """
    stmt = select(Student).where(Student.id == student_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        raise StudentNotFound()

    student.is_active = False

    user_stmt = select(User).where(User.id == student.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user:
        user.is_active = False

    await db.commit()


async def add_to_group(
    db: AsyncSession,
    student_id: uuid.UUID,
    group_id: uuid.UUID,
) -> None:
    """O'quvchini guruhga qo'shish. Agar avval bo'lgan bo'lsa — qayta faollashtirish."""
    stmt = select(StudentGroup).where(
        and_(
            StudentGroup.student_id == student_id,
            StudentGroup.group_id == group_id,
        )
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.is_active = True
        existing.left_at = None
    else:
        db.add(StudentGroup(student_id=student_id, group_id=group_id))

    await db.commit()


async def remove_from_group(
    db: AsyncSession,
    student_id: uuid.UUID,
    group_id: uuid.UUID,
) -> None:
    """O'quvchini guruhdan chiqarish (soft: is_active = False)."""
    stmt = select(StudentGroup).where(
        and_(
            StudentGroup.student_id == student_id,
            StudentGroup.group_id == group_id,
        )
    )
    sg = (await db.execute(stmt)).scalar_one_or_none()
    if sg:
        sg.is_active = False
        sg.left_at = date.today()
        await db.commit()
