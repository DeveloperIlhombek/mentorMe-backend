"""
app/api/v1/student_routes.py

O'quvchi paneli endpointlari:
  GET /student/profile        — o'z profili
  GET /student/groups         — guruhlari va jadval
  GET /student/attendance     — davomat tarixi
  GET /student/gamification   — XP, level, streak
  GET /student/leaderboard    — reyting
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_student
from app.models.tenant import Student, User
from app.schemas import ok
from app.services import attendance as att_svc
from app.services import gamification as gam_svc
from app.services import group as group_svc

router = APIRouter(prefix="/student", tags=["student"])


async def _get_student(db: AsyncSession, user_id: uuid.UUID) -> Optional[Student]:
    stmt = select(Student).where(Student.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get("/profile")
async def get_profile(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_student),
):
    """O'quvchining o'z profili."""
    user_id = uuid.UUID(tkn["sub"])
    stmt    = select(User).where(User.id == user_id)
    user    = (await db.execute(stmt)).scalar_one_or_none()
    student = await _get_student(db, user_id)

    from app.services import student as student_svc
    if student:
        data = await student_svc.get_by_id(db, student.id)
        return ok(data)

    return ok({
        "user_id":    str(user_id),
        "first_name": user.first_name if user else "",
        "last_name":  user.last_name if user else "",
    })


@router.get("/groups")
async def get_my_groups(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_student),
):
    """O'quvchining guruhlari."""
    user_id = uuid.UUID(tkn["sub"])
    student = await _get_student(db, user_id)
    if not student:
        return ok([])

    groups, _ = await group_svc.get_groups(db, per_page=50)
    # Filter: faqat student o'z guruhlarini ko'radi
    from app.models.tenant import StudentGroup
    stmt = select(StudentGroup.group_id).where(
        and_(StudentGroup.student_id == student.id, StudentGroup.is_active == True)
    )
    my_group_ids = {str(row[0]) for row in (await db.execute(stmt)).all()}
    my_groups = [g for g in groups if g["id"] in my_group_ids]
    return ok(my_groups)


@router.get("/attendance")
async def get_my_attendance(
    month: Optional[int] = Query(None, ge=1, le=12),
    year:  Optional[int] = Query(None),
    db:    AsyncSession  = Depends(get_tenant_session),
    tkn:   dict          = Depends(require_student),
):
    """O'quvchining davomat tarixi."""
    user_id = uuid.UUID(tkn["sub"])
    student = await _get_student(db, user_id)
    if not student:
        return ok({"records": [], "summary": {}})

    result = await att_svc.get_student_history(db, student.id, month, year)
    return ok(result)


@router.get("/gamification")
async def get_my_gamification(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_student),
):
    """XP, daraja, streak, xp tarixi."""
    user_id = uuid.UUID(tkn["sub"])
    student = await _get_student(db, user_id)
    if not student:
        return ok({"profile": {}, "history": []})

    profile = await gam_svc.get_profile(db, student.id)
    history = await gam_svc.get_xp_history(db, student.id)
    return ok({"profile": profile, "history": history})
