"""app/api/v1/admin/trash.py — Savatcha endpointlari."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin
from app.core.security import hash_password
from app.models.tenant import Student, Teacher, User
from app.models.tenant.group import Group
from app.schemas import ok

router = APIRouter(prefix="/trash", tags=["trash"])


# ─── Yordamchi ───────────────────────────────────────────────────────

def _user_dict(u: User) -> dict:
    return {
        "id":         str(u.id),
        "first_name": u.first_name,
        "last_name":  u.last_name,
        "phone":      u.phone,
        "email":      u.email,
        "role":       u.role,
        "deleted_at": u.deleted_at.isoformat() if u.deleted_at else None,
    }


# ─── O'quvchilar ─────────────────────────────────────────────────────

@router.get("/students")
async def list_deleted_students(
    search:   Optional[str] = Query(None),
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=100),
    db: AsyncSession        = Depends(get_tenant_session),
    _:  dict                = Depends(require_admin),
):
    """O'chirilgan o'quvchilar."""
    from sqlalchemy import func
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.is_active == False)
    )
    if search:
        q = f"%{search}%"
        stmt = stmt.where(or_(
            User.first_name.ilike(q), User.last_name.ilike(q), User.phone.ilike(q)
        ))
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    rows = (await db.execute(stmt.offset((page-1)*per_page).limit(per_page))).all()

    data = [{
        "id":         str(s.id),
        "user_id":    str(s.user_id),
        "first_name": u.first_name,
        "last_name":  u.last_name,
        "phone":      u.phone,
        "email":      u.email,
        "deleted_at": getattr(s, "deleted_at", None),
        "type":       "student",
    } for s, u in rows]
    return ok(data, {"total": total, "page": page, "per_page": per_page})


@router.post("/students/{student_id}/restore")
async def restore_student(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'quvchini tiklash."""
    stmt    = select(Student).where(Student.id == student_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "O'quvchi topilmadi")

    student.is_active = True
    if hasattr(student, 'deleted_at'):
        student.deleted_at = None

    # User ni ham faollashtirish
    user_stmt = select(User).where(User.id == student.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user:
        user.is_active = True

    await db.commit()
    return ok({"message": "O'quvchi tiklandi", "id": str(student_id)})


@router.delete("/students/{student_id}")
async def permanent_delete_student(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'quvchini doimiy o'chirish — bog'liq yozuvlar ham o'chiriladi."""
    from sqlalchemy import delete as sql_delete
    from sqlalchemy import text

    from app.models.tenant.attendance import Attendance
    from app.models.tenant.gamification import (
        GamificationProfile,
        StudentAchievement,
        XpTransaction,
    )
    from app.models.tenant.payment import Payment
    from app.models.tenant.student import StudentGroup

    stmt    = select(Student).where(Student.id == student_id, Student.is_active == False)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "Nofaol o'quvchi topilmadi")

    user_id = student.user_id

    # Bog'liq yozuvlarni tartib bilan o'chirish (FK constraint)
    # Bog'liq yozuvlar tartib bilan (FK teskari tartibda)
    await db.execute(sql_delete(StudentAchievement).where(StudentAchievement.student_id == student_id))
    await db.execute(sql_delete(XpTransaction).where(XpTransaction.student_id == student_id))
    await db.execute(sql_delete(GamificationProfile).where(GamificationProfile.student_id == student_id))
    await db.execute(sql_delete(Attendance).where(Attendance.student_id == student_id))
    await db.execute(sql_delete(Payment).where(Payment.student_id == student_id))
    await db.execute(sql_delete(StudentGroup).where(StudentGroup.student_id == student_id))
    await db.flush()
    await db.delete(student)
    await db.flush()

    # User + notifications ni o'chirish
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user:
        from app.models.tenant.notification import Notification
        await db.execute(sql_delete(Notification).where(Notification.user_id == user_id))
        await db.flush()
        await db.delete(user)

    await db.commit()
    return ok({"message": "Doimiy o'chirildi"})


# ─── O'qituvchilar ────────────────────────────────────────────────────

@router.get("/teachers")
async def list_deleted_teachers(
    search:   Optional[str] = Query(None),
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=100),
    db: AsyncSession        = Depends(get_tenant_session),
    _:  dict                = Depends(require_admin),
):
    from sqlalchemy import func
    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.is_active == False)
    )
    if search:
        q = f"%{search}%"
        stmt = stmt.where(or_(User.first_name.ilike(q), User.last_name.ilike(q)))
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    rows = (await db.execute(stmt.offset((page-1)*per_page).limit(per_page))).all()

    data = [{
        "id":         str(t.id),
        "first_name": u.first_name,
        "last_name":  u.last_name,
        "phone":      u.phone,
        "subjects":   t.subjects,
        "type":       "teacher",
    } for t, u in rows]
    return ok(data, {"total": total, "page": page})


@router.post("/teachers/{teacher_id}/restore")
async def restore_teacher(
    teacher_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    stmt    = select(Teacher).where(Teacher.id == teacher_id)
    teacher = (await db.execute(stmt)).scalar_one_or_none()
    if not teacher:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "O'qituvchi topilmadi")
    teacher.is_active = True
    user = (await db.execute(select(User).where(User.id == teacher.user_id))).scalar_one_or_none()
    if user:
        user.is_active = True
    await db.commit()
    return ok({"message": "O'qituvchi tiklandi", "id": str(teacher_id)})


@router.delete("/teachers/{teacher_id}")
async def permanent_delete_teacher(
    teacher_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """O'qituvchini doimiy o'chirish."""
    from sqlalchemy import delete as sql_delete

    from app.models.tenant.attendance import Attendance
    from app.models.tenant.group import Group

    stmt    = select(Teacher).where(Teacher.id == teacher_id, Teacher.is_active == False)
    teacher = (await db.execute(stmt)).scalar_one_or_none()
    if not teacher:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "Nofaol o'qituvchi topilmadi")

    user_id = teacher.user_id

    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(Group).where(Group.teacher_id == teacher_id).values(teacher_id=None)
    )
    # Davomat yozuvlaridan teacher_id ni tozalash
    await db.execute(
        sql_update(Attendance).where(Attendance.teacher_id == teacher_id).values(teacher_id=None)
    )

    await db.delete(teacher)
    await db.flush()

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user:
        await db.delete(user)

    await db.commit()
    return ok({"message": "Doimiy o'chirildi"})


# ─── Guruhlar ─────────────────────────────────────────────────────────

@router.get("/groups")
async def list_deleted_groups(
    search:   Optional[str] = Query(None),
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=100),
    db: AsyncSession        = Depends(get_tenant_session),
    _:  dict                = Depends(require_admin),
):
    from sqlalchemy import func
    stmt = select(Group).where(Group.status.in_(["completed", "paused"]))
    if search:
        stmt = stmt.where(Group.name.ilike(f"%{search}%"))
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    rows = (await db.execute(stmt.offset((page-1)*per_page).limit(per_page))).scalars().all()

    data = [{
        "id":          str(g.id),
        "name":        g.name,
        "subject":     g.subject,
        "status":      g.status,
        "type":        "group",
    } for g in rows]
    return ok(data, {"total": total, "page": page})


@router.post("/groups/{group_id}/restore")
async def restore_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    stmt  = select(Group).where(Group.id == group_id)
    group = (await db.execute(stmt)).scalar_one_or_none()
    if not group:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "Guruh topilmadi")
    group.status = "active"
    await db.commit()
    return ok({"message": "Guruh tiklandi", "id": str(group_id)})


@router.delete("/groups/{group_id}")
async def permanent_delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Guruhni doimiy o'chirish (faqat nofaol guruhlar)."""
    stmt  = select(Group).where(Group.id == group_id, Group.status.in_(["completed", "paused"]))
    group = (await db.execute(stmt)).scalar_one_or_none()
    if not group:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "Nofaol guruh topilmadi")
    await db.delete(group)
    await db.commit()
    return ok({"message": "Guruh doimiy o'chirildi"})


# ─── Umumiy statistika ────────────────────────────────────────────────

@router.get("/stats")
async def trash_stats(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Savatchadagi elementlar soni."""
    from sqlalchemy import func
    students = (await db.execute(
        select(func.count(Student.id)).where(Student.is_active == False)
    )).scalar_one()
    teachers = (await db.execute(
        select(func.count(Teacher.id)).where(Teacher.is_active == False)
    )).scalar_one()
    groups = (await db.execute(
        select(func.count(Group.id)).where(Group.status.in_(["completed", "paused"]))
    )).scalar_one()
    return ok({
        "students": students,
        "teachers": teachers,
        "groups":   groups,
        "total":    students + teachers + groups,
    })
