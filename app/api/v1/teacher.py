"""
app/api/v1/teacher.py

O'qituvchi endpointlari:
  GET  /teacher/me           — o'z profili
  GET  /teacher/groups       — o'z guruhlari
  GET  /teacher/schedule     — bugungi jadval
  POST /teacher/attendance   — davomat kiritish (guruh uchun)
"""
import datetime as _dt
import uuid
from datetime import date
from typing import List as _List
from typing import Optional
from typing import Optional as _Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as _BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_teacher
from app.models.tenant import Group, Notification, Teacher, User
from app.schemas import ok
from app.schemas.attendance import AttendanceItem
from app.schemas.student import StudentCreate
from app.services import attendance as att_svc
from app.services import group as group_svc
from app.services import student as student_svc


class _TeacherAttendanceCreate(_BaseModel):
    group_id: uuid.UUID
    date:     _Optional[_dt.date] = None
    # frontend 'items' yuboradi, schema 'records' kutadi — ikkisini qabul qilamiz
    items:    _Optional[_List[AttendanceItem]] = None
    records:  _Optional[_List[AttendanceItem]] = None

    def get_records(self) -> _List[AttendanceItem]:
        return self.records or self.items or []

router = APIRouter(prefix="/teacher", tags=["teacher"])


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID) -> Optional[Teacher]:
    stmt = select(Teacher).where(Teacher.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get("/me")
async def get_my_profile(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """O'qituvchining o'z profili."""
    user_id = uuid.UUID(tkn["sub"])
    stmt    = select(User).where(User.id == user_id)
    user    = (await db.execute(stmt)).scalar_one_or_none()
    teacher = await _get_teacher(db, user_id)

    return ok({
        "user_id":       str(user_id),
        "first_name":    user.first_name if user else "",
        "last_name":     user.last_name  if user else "",
        "email":         user.email      if user else None,
        "phone":         user.phone      if user else None,
        "subjects":      teacher.subjects      if teacher else [],
        "bio":           teacher.bio           if teacher else None,
        "salary_type":   teacher.salary_type   if teacher else None,
        "salary_amount": float(teacher.salary_amount) if teacher and teacher.salary_amount else None,
        "language_code": user.language_code if user else "uz",
    })


class _ProfileUpdate(_BaseModel):
    first_name:    Optional[str] = None
    last_name:     Optional[str] = None
    phone:         Optional[str] = None
    email:         Optional[str] = None
    bio:           Optional[str] = None
    language_code: Optional[str] = None


from pydantic import BaseModel as _BaseModel_  # noqa


@router.patch("/me")
async def update_my_profile(
    data: _ProfileUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """O'qituvchining profilini yangilash."""
    user_id = uuid.UUID(tkn["sub"])
    user    = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    teacher = await _get_teacher(db, user_id)

    if not user:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "USER_NOT_FOUND", "Foydalanuvchi topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        if field == "bio" and teacher:
            teacher.bio = value
        elif hasattr(user, field):
            setattr(user, field, value)

    from datetime import datetime
    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    return ok({
        "user_id":    str(user.id),
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "email":      user.email,
        "phone":      user.phone,
        "bio":        teacher.bio if teacher else None,
        "language_code": user.language_code,
    })


class _ChangePassword(_BaseModel_):
    current_password: str
    new_password:     str


@router.post("/me/change-password")
async def change_password(
    data: _ChangePassword,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """Parolni o'zgartirish."""
    from app.core.security import hash_password, verify_password

    user_id = uuid.UUID(tkn["sub"])
    user    = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    if not user or not user.password_hash:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(400, "NO_PASSWORD", "Parol o'rnatilmagan")

    if not verify_password(data.current_password, user.password_hash):
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(400, "WRONG_PASSWORD", "Joriy parol noto'g'ri")

    if len(data.new_password) < 8:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(400, "WEAK_PASSWORD", "Parol kamida 8 ta belgi bo'lishi kerak")

    user.password_hash = hash_password(data.new_password)
    await db.commit()
    return ok({"changed": True})


@router.get("/groups")
async def get_my_groups(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """O'qituvchining guruhlari."""
    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)
    if not teacher:
        return ok([])

    groups, _ = await group_svc.get_groups(
        db, per_page=100, teacher_id=teacher.id
    )
    return ok(groups)


@router.get("/schedule")
async def get_today_schedule(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """Bugungi darslar jadvali (attendance_done + students_count + extra darslar)."""
    from app.models.tenant.attendance import Attendance
    from app.models.tenant.student import StudentGroup

    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)
    if not teacher:
        return ok([])

    today       = date.today()
    today_wd    = today.isoweekday()   # 1=Du … 7=Ya

    # Faol guruhlar
    stmt = select(Group).where(
        and_(Group.teacher_id == teacher.id, Group.status == "active")
    )
    groups = (await db.execute(stmt)).scalars().all()

    today_lessons = []
    for g in groups:
        # O'quvchilar soni
        sc_stmt = select(func.count()).select_from(
            select(StudentGroup).where(
                and_(StudentGroup.group_id == g.id, StudentGroup.is_active == True)
            ).subquery()
        )
        students_count = (await db.execute(sc_stmt)).scalar_one() or 0

        # Davomat kiritilganmi?
        att_stmt = select(Attendance).where(
            and_(Attendance.group_id == g.id, Attendance.date == today)
        ).limit(1)
        attendance_done = bool((await db.execute(att_stmt)).first())

        if g.schedule:
            for slot in g.schedule:
                if slot.get("day") == today_wd:
                    today_lessons.append({
                        "group_id":       str(g.id),
                        "group_name":     g.name,
                        "subject":        g.subject,
                        "start":          slot.get("start"),
                        "end":            slot.get("end"),
                        "room":           slot.get("room"),
                        "students_count": students_count,
                        "attendance_done":attendance_done,
                        "is_extra":       False,
                    })

    # Extra darslar — lesson_cancellations.adj_type='extra' va lesson_date=today
    try:
        from app.models.tenant.lesson_cancellation import LessonCancellation
        extra_stmt = (
            select(LessonCancellation, Group)
            .join(Group, LessonCancellation.group_id == Group.id)
            .where(
                and_(
                    LessonCancellation.lesson_date == today,
                    Group.teacher_id == teacher.id,
                )
            )
        )
        extra_rows = (await db.execute(extra_stmt)).all()
        seen_extra = {(str(lc.group_id), lc.lesson_date) for lc, _ in extra_rows}
        for lc, g in extra_rows:
            # Jadvalda allaqachon ko'rsatilmagan bo'lsa
            key = (str(g.id), today)
            slot = (g.schedule or [{}])[0]
            today_lessons.append({
                "group_id":       str(g.id),
                "group_name":     g.name,
                "subject":        g.subject,
                "start":          slot.get("start", ""),
                "end":            slot.get("end", ""),
                "room":           slot.get("room"),
                "students_count": 0,
                "attendance_done":False,
                "is_extra":       True,
                "reason":         lc.reason,
            })
    except Exception:
        pass   # jadval yo'q bo'lsa e'tiborsiz

    today_lessons.sort(key=lambda x: x.get("start") or "")
    return ok(today_lessons)


@router.post("/attendance", status_code=201)
async def submit_attendance(
    data: _TeacherAttendanceCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """Davomat kiritish (o'qituvchi tomonidan)."""
    import datetime

    from app.schemas.attendance import AttendanceBulkCreate

    user_id    = uuid.UUID(tkn["sub"])
    teacher    = await _get_teacher(db, user_id)
    teacher_id = teacher.id if teacher else None

    bulk = AttendanceBulkCreate(
        group_id = data.group_id,
        date     = data.date or datetime.date.today(),
        records  = data.get_records(),
    )
    result = await att_svc.bulk_create(db, bulk, teacher_id)
    return ok(result)


# ─── Teacher: o'quvchi yaratish ──────────────────────────────────────

@router.post("/students", status_code=201)
async def teacher_create_student(
    data: StudentCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """
    Teacher tomonidan o'quvchi yaratish.
    is_approved=False → admin tasdiqlashini kutadi.
    Admin barcha o'quvchilarga notification oladi.
    """
    created_by = uuid.UUID(tkn["sub"])

    result = await student_svc.create(
        db, data,
        created_by=created_by,
        role="teacher",
    )

    # Admin larga notification yuborish
    admin_stmt = select(User).where(User.role == "admin", User.is_active.is_(True))
    admins = (await db.execute(admin_stmt)).scalars().all()
    student_name = f"{data.first_name} {data.last_name or ''}".strip()

    for admin in admins:
        db.add(Notification(
            user_id=admin.id,
            type="student_pending",
            title="Yangi o'quvchi — tasdiqlash kerak",
            body=f"O'qituvchi {student_name} nomli yangi o'quvchi qo'shdi. Tasdiqlang.",
            data={"student_id": result.get("id", "")},
            channel="telegram",
        ))
    await db.commit()

    return ok({**result, "pending": True,
               "message": "O'quvchi yaratildi. Admin tasdiqlashini kuting."})


# ─── Teacher: guruhga o'quvchi qo'shish/o'chirish ────────────────────

class _EnrollBody(_BaseModel):
    student_id: uuid.UUID

@router.post("/groups/{group_id}/enroll", status_code=201)
async def teacher_enroll_student(
    group_id: uuid.UUID,
    body:     _EnrollBody,
    db:       AsyncSession  = Depends(get_tenant_session),
    tkn:      dict          = Depends(require_teacher),
):
    """
    Teacher o'z guruhiga o'quvchi qo'shish so'rovi.
    Admin/inspektor tasdiqlashi kerak (StudentGroup pending = is_approved=False).
    Bildirishnoma: admin + inspektorlarga yuboriladi.
    """
    from sqlalchemy import and_
    from app.models.tenant.student import Student, StudentGroup

    teacher_user_id = uuid.UUID(tkn["sub"])

    # Teacher o'z guruhiga qo'shishi mumkin (tekshirish)
    teacher_stmt = select(Teacher).where(Teacher.user_id == teacher_user_id)
    teacher = (await db.execute(teacher_stmt)).scalar_one_or_none()
    if not teacher:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Teacher topilmadi")

    group = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not group:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Guruh topilmadi")

    if group.teacher_id and group.teacher_id != teacher.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Bu sizning guruhingiz emas")

    # Mavjud enrollment tekshirish
    existing = (await db.execute(
        select(StudentGroup).where(
            and_(StudentGroup.student_id == body.student_id,
                 StudentGroup.group_id == group_id)
        )
    )).scalar_one_or_none()

    if existing and existing.is_active:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="O'quvchi allaqachon guruhda")

    if existing:
        existing.is_active = True
        existing.left_at = None
    else:
        db.add(StudentGroup(
            student_id=body.student_id,
            group_id=group_id,
        ))
    await db.commit()

    # Bildirishnoma: admin + inspektorlarga
    try:
        from bot.utils.notify import notify_group_enrollment
        student = (await db.execute(select(Student).where(Student.id == body.student_id))).scalar_one_or_none()
        caller  = (await db.execute(select(User).where(User.id == teacher_user_id))).scalar_one_or_none()
        if student:
            student_user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
            s_name = f"{student_user.first_name} {student_user.last_name or ''}".strip() if student_user else "O'quvchi"
            c_name = f"{caller.first_name} {caller.last_name or ''}".strip() if caller else ""
            import asyncio
            asyncio.create_task(notify_group_enrollment(
                tenant_schema=tkn.get("tenant_slug", "default"),
                student_name=s_name,
                group_name=group.name,
                action="pending",
                by_name=c_name,
                by_role="teacher",
            ))
    except Exception:
        pass

    return ok({"message": "So'rov yuborildi. Admin tasdiqlashini kuting."})


@router.delete("/groups/{group_id}/students/{student_id}", status_code=204)
async def teacher_remove_student(
    group_id:   uuid.UUID,
    student_id: uuid.UUID,
    db:         AsyncSession = Depends(get_tenant_session),
    tkn:        dict         = Depends(require_teacher),
):
    """Teacher o'z guruhidan o'quvchini chiqarish."""
    teacher_user_id = uuid.UUID(tkn["sub"])
    teacher = (await db.execute(select(Teacher).where(Teacher.user_id == teacher_user_id))).scalar_one_or_none()
    if not teacher:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Teacher topilmadi")

    group = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not group:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Guruh topilmadi")

    if group.teacher_id and group.teacher_id != teacher.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Bu sizning guruhingiz emas")

    from app.services.student import remove_from_group
    await remove_from_group(db, student_id, group_id)

    # Bildirishnoma
    try:
        from bot.utils.notify import notify_group_enrollment
        from app.models.tenant.student import Student
        student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
        caller  = (await db.execute(select(User).where(User.id == teacher_user_id))).scalar_one_or_none()
        if student and group:
            student_user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
            s_name = f"{student_user.first_name} {student_user.last_name or ''}".strip() if student_user else "O'quvchi"
            c_name = f"{caller.first_name} {caller.last_name or ''}".strip() if caller else ""
            import asyncio
            asyncio.create_task(notify_group_enrollment(
                tenant_schema=tkn.get("tenant_slug", "default"),
                student_name=s_name,
                group_name=group.name,
                action="removed",
                by_name=c_name,
                by_role="teacher",
            ))
    except Exception:
        pass


# ─── Teacher: guruh o'quvchilari ─────────────────────────────────────

@router.get("/groups/{group_id}/students")
async def get_group_students(
    group_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """Guruh o'quvchilari (davomat kiritish uchun)."""
    from app.services.student import get_students
    students, _ = await get_students(db, group_id=group_id, per_page=100)
    return ok(students)


@router.get("/students/{student_id}")
async def get_student_detail(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_teacher),
):
    """O'quvchi profili — teacher uchun (progress sahifasida ishlatiladi)."""
    from app.services.student import get_by_id
    from app.core.exceptions import StudentNotFound
    try:
        data = await get_by_id(db, student_id)
    except StudentNotFound:
        raise
    return ok(data)


@router.get("/groups/{group_id}/attendance")
async def get_group_attendance(
    group_id: uuid.UUID,
    date_val: Optional[date] = None,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """Guruhning ma'lum kündagi davomati."""
    if not date_val:
        date_val = date.today()
    records = await att_svc.get_by_group_date(db, group_id, date_val)
    return ok(records)


# ─── Teacher: KPI ────────────────────────────────────────────────────

@router.get("/kpi")
async def get_my_kpi(
    month: Optional[int] = None,
    year:  Optional[int] = None,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """O'qituvchining KPI natijalari va maosh sliplari."""
    from app.services.kpi import get_payslips, get_results
    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)
    if not teacher:
        return ok({"results": [], "payslips": []})

    results  = await get_results(db, teacher.id, month, year)
    payslips = await get_payslips(db, teacher.id, month, year)
    return ok({"results": results, "payslips": payslips})


# ─── Teacher: o'quvchi statistika ────────────────────────────────────

@router.get("/stats")
async def get_my_stats(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """O'qituvchining umumiy statistikasi."""
    from datetime import date

    from sqlalchemy import extract, func

    from app.models.tenant.attendance import Attendance
    from app.models.tenant.student import Student, StudentGroup

    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)
    if not teacher:
        return ok({})

    today = date.today()
    groups, total_groups = await group_svc.get_groups(
        db, per_page=100, teacher_id=teacher.id
    )
    group_ids = [uuid.UUID(g["id"]) for g in groups]

    # Jami o'quvchilar
    total_students = 0
    if group_ids:
        total_students = (await db.execute(
            select(func.count(StudentGroup.id)).where(
                StudentGroup.group_id.in_(group_ids),
                StudentGroup.is_active == True,
            )
        )).scalar_one()

    # Bu oy davomati
    present_count = 0
    total_att = 0
    if group_ids:
        total_att = (await db.execute(
            select(func.count(Attendance.id)).where(
                Attendance.group_id.in_(group_ids),
                extract("month", Attendance.date) == today.month,
                extract("year",  Attendance.date) == today.year,
            )
        )).scalar_one()
        present_count = (await db.execute(
            select(func.count(Attendance.id)).where(
                Attendance.group_id.in_(group_ids),
                Attendance.status.in_(["present", "late"]),
                extract("month", Attendance.date) == today.month,
                extract("year",  Attendance.date) == today.year,
            )
        )).scalar_one()

    return ok({
        "group_count":    total_groups,
        "student_count":  total_students,
        "attendance_pct": round(present_count / total_att * 100, 1) if total_att else 0,
        "this_month":     {"present": present_count, "total": total_att},
    })
