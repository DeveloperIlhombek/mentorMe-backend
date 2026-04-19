"""
app/api/v1/admin/teachers.py

O'qituvchilar boshqaruvi.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_inspector, require_teacher, get_optional_branch_filter
from app.core.exceptions import StudentNotFound
from app.core.security import hash_password
from app.models.tenant import Branch, Teacher, User
from app.schemas import ok

router = APIRouter(prefix="/teachers", tags=["teachers"])


# ─── Schemas (inline, kichik modul) ──────────────────────────────────
from pydantic import BaseModel, EmailStr
from typing import List

class TeacherCreate(BaseModel):
    first_name:    str
    last_name:     Optional[str]  = None
    phone:         Optional[str]  = None
    email:         Optional[EmailStr] = None
    subjects:      Optional[List[str]] = None
    bio:           Optional[str]  = None
    salary_type:   Optional[str]  = None   # fixed | percent | per_lesson
    salary_amount: Optional[float] = None
    branch_id:     Optional[uuid.UUID] = None

class TeacherUpdate(BaseModel):
    first_name:    Optional[str]  = None
    last_name:     Optional[str]  = None
    phone:         Optional[str]  = None
    email:         Optional[EmailStr] = None
    subjects:      Optional[List[str]] = None
    bio:           Optional[str]  = None
    salary_type:   Optional[str]  = None
    salary_amount: Optional[float] = None
    branch_id:     Optional[uuid.UUID] = None
    is_active:     Optional[bool] = None


# ─── Yordamchi ───────────────────────────────────────────────────────
async def _teacher_dict(teacher: Teacher, user: User) -> dict:
    return {
        "id":               str(teacher.id),
        "user_id":          str(teacher.user_id),
        "first_name":       user.first_name,
        "last_name":        user.last_name,
        "phone":            user.phone,
        "email":            user.email,
        "avatar_url":       user.avatar_url,
        "is_active":        teacher.is_active,
        "is_approved":      teacher.is_approved,
        "created_by":       str(teacher.created_by) if teacher.created_by else None,
        "created_by_role":  teacher.created_by_role,
        "subjects":         teacher.subjects or [],
        "bio":              teacher.bio,
        "salary_type":      teacher.salary_type,
        "salary_amount":    float(teacher.salary_amount) if teacher.salary_amount else None,
        "branch_id":        str(teacher.branch_id) if teacher.branch_id else None,
        "hired_at":         teacher.hired_at.isoformat() if teacher.hired_at else None,
        "created_at":       teacher.created_at.isoformat(),
    }


# ─── Endpointlar ─────────────────────────────────────────────────────
@router.get("")
async def list_teachers(
    page:        int           = Query(1, ge=1),
    per_page:    int           = Query(20, ge=1, le=100),
    search:      Optional[str] = Query(None),
    is_active:   Optional[bool]= Query(None),
    is_approved: Optional[bool]= Query(None),
    db: AsyncSession           = Depends(get_tenant_session),
    _:  dict                   = Depends(require_teacher),
    branch_filter: Optional[str] = Depends(get_optional_branch_filter),
):
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
    )
    if is_active is not None:
        stmt = stmt.where(Teacher.is_active == is_active)
    if is_approved is not None:
        stmt = stmt.where(Teacher.is_approved == is_approved)
    if branch_filter:
        stmt = stmt.where(Teacher.branch_id == uuid.UUID(branch_filter))
    if search:
        q = f"%{search}%"
        stmt = stmt.where(or_(User.first_name.ilike(q), User.last_name.ilike(q), User.phone.ilike(q)))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt  = stmt.order_by(User.first_name).offset((page-1)*per_page).limit(per_page)
    rows  = (await db.execute(stmt)).all()

    data  = [await _teacher_dict(t, u) for t, u in rows]
    pages = (total + per_page - 1) // per_page
    return ok(data, {"page": page, "per_page": per_page, "total": total, "total_pages": pages})


@router.post("", status_code=201)
async def create_teacher(
    data: TeacherCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_inspector),
):
    caller_role = tkn.get("role", "")
    caller_id   = uuid.UUID(tkn["sub"])

    # Admin/super_admin tomonidan yaratilsa — darhol tasdiqlangan
    # Inspector tomonidan yaratilsa — admin tasdiqlashini kutadi
    is_approved = caller_role in ("admin", "super_admin")

    # User yaratish — pending bo'lsa is_active=False
    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        email=data.email,
        role="teacher",
        password_hash=hash_password("Teacher123!"),
        is_active=is_approved,  # Pending holatda login qila olmaydi
    )
    db.add(user)
    await db.flush()

    # Teacher yaratish
    teacher = Teacher(
        user_id=user.id,
        branch_id=data.branch_id,
        subjects=data.subjects,
        bio=data.bio,
        salary_type=data.salary_type,
        salary_amount=data.salary_amount,
        is_approved=is_approved,
        created_by=caller_id,
        created_by_role=caller_role,
    )
    db.add(teacher)
    await db.commit()

    return ok(await _teacher_dict(teacher, user), {"pending_approval": not is_approved})


@router.get("/{teacher_id}")
async def get_teacher(
    teacher_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.id == teacher_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "TEACHER_NOT_FOUND", "O'qituvchi topilmadi")
    return ok(await _teacher_dict(row[0], row[1]))


@router.patch("/{teacher_id}")
async def update_teacher(
    teacher_id: uuid.UUID,
    data: TeacherUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.id == teacher_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "TEACHER_NOT_FOUND", "O'qituvchi topilmadi")

    teacher, user = row

    if data.first_name    is not None: user.first_name     = data.first_name
    if data.last_name     is not None: user.last_name      = data.last_name
    if data.phone         is not None: user.phone          = data.phone
    if data.email         is not None: user.email          = data.email
    if data.subjects      is not None: teacher.subjects    = data.subjects
    if data.bio           is not None: teacher.bio         = data.bio
    if data.salary_type   is not None: teacher.salary_type = data.salary_type
    if data.salary_amount is not None: teacher.salary_amount = data.salary_amount
    if data.branch_id     is not None: teacher.branch_id   = data.branch_id
    if data.is_active     is not None:
        teacher.is_active = data.is_active
        user.is_active    = data.is_active

    await db.commit()
    return ok(await _teacher_dict(teacher, user))


@router.delete("/{teacher_id}", status_code=204)
async def delete_teacher(
    teacher_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    stmt = select(Teacher).where(Teacher.id == teacher_id)
    teacher = (await db.execute(stmt)).scalar_one_or_none()
    if teacher:
        teacher.is_active = False
        user_stmt = select(User).where(User.id == teacher.user_id)
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        if user:
            user.is_active = False
        await db.commit()


@router.get("/pending")
async def list_pending_teachers(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Tasdiqlashni kutayotgan o'qituvchilar ro'yxati (faqat admin ko'radi)."""
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.is_approved == False)
        .order_by(Teacher.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return ok([await _teacher_dict(t, u) for t, u in rows])


@router.post("/{teacher_id}/approve")
async def approve_teacher(
    teacher_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    """Admin o'qituvchini tasdiqlaydi — is_approved=True, is_active=True."""
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.id == teacher_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "TEACHER_NOT_FOUND", "O'qituvchi topilmadi")

    teacher, user = row
    teacher.is_approved = True
    user.is_active      = True
    teacher.is_active   = True
    await db.commit()
    return ok(await _teacher_dict(teacher, user))


@router.post("/{teacher_id}/reject")
async def reject_teacher(
    teacher_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    """Admin o'qituvchini rad etadi — user va teacher o'chiriladi."""
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.id == teacher_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "TEACHER_NOT_FOUND", "O'qituvchi topilmadi")

    teacher, user = row
    await db.delete(teacher)
    await db.delete(user)
    await db.commit()
    return ok({"deleted": str(teacher_id)})


@router.get("/{teacher_id}/salary-report")
async def salary_report(
    teacher_id: uuid.UUID,
    month: int = Query(..., ge=1, le=12),
    year:  int = Query(...),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'qituvchi ish haqi hisoboti."""
    from app.models.tenant import Group
    from sqlalchemy import extract

    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.id == teacher_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "TEACHER_NOT_FOUND", "O'qituvchi topilmadi")

    teacher, user = row

    # Guruhlar soni
    groups_stmt = select(func.count(Group.id)).where(
        and_(Group.teacher_id == teacher_id, Group.status == "active")
    )
    groups_count = (await db.execute(groups_stmt)).scalar_one()

    # Davomat kunlari soni (shu oyda dars o'tgan)
    from app.models.tenant import Attendance
    att_stmt = select(func.count(Attendance.id.distinct())).where(
        and_(
            Attendance.teacher_id == teacher_id,
            extract("month", Attendance.date) == month,
            extract("year",  Attendance.date) == year,
        )
    )
    lessons_count = (await db.execute(att_stmt)).scalar_one()

    salary = float(teacher.salary_amount or 0)

    return ok({
        "teacher_id":     str(teacher_id),
        "first_name":     user.first_name,
        "last_name":      user.last_name,
        "salary_type":    teacher.salary_type,
        "salary_amount":  salary,
        "groups_count":   groups_count,
        "lessons_count":  lessons_count,
        "month":          month,
        "year":           year,
        "calculated_salary": salary if teacher.salary_type == "fixed" else salary * lessons_count,
    })
