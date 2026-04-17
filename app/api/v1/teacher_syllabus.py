"""
app/api/v1/teacher_syllabus.py
O'qituvchi uchun Syllabus + Leaderboard + Notifications + Student requests
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_teacher
from app.models.tenant.user import User
from app.models.tenant.notification import Notification
from app.models.tenant import Teacher
from app.schemas import ok
from app.services import syllabus as syl_svc

router = APIRouter(tags=["teacher-syllabus"])


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID):
    stmt = select(Teacher).where(Teacher.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


# ══════════════════════════════════════════════════════════════════════
# SYLLABUS (O'quv yo'li) CRUD
# ══════════════════════════════════════════════════════════════════════

class SyllabusCreate(BaseModel):
    title:        str
    description:  Optional[str] = None
    subject:      Optional[str] = None
    xp_per_topic: int = 50
    color:        str = "#4f8ef7"
    icon:         str = "📚"


class SyllabusUpdate(BaseModel):
    title:        Optional[str] = None
    description:  Optional[str] = None
    subject:      Optional[str] = None
    xp_per_topic: Optional[int] = None
    color:        Optional[str] = None
    icon:         Optional[str] = None
    status:       Optional[str] = None


class TopicCreate(BaseModel):
    title:       str
    description: Optional[str] = None
    xp_reward:   int = 50
    order_index: Optional[int] = None


class TopicUpdate(BaseModel):
    title:       Optional[str] = None
    description: Optional[str] = None
    xp_reward:   Optional[int] = None
    order_index: Optional[int] = None


class ReorderTopics(BaseModel):
    topic_ids: List[uuid.UUID]


class AssignRequest(BaseModel):
    target_type: str       # group | student
    target_id:   uuid.UUID


class CompleteTopicRequest(BaseModel):
    student_ids: List[uuid.UUID]


# ── Syllabuslar ───────────────────────────────────────────────────────

@router.get("/teacher/syllabuses")
async def list_syllabuses(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    user_id = uuid.UUID(tkn["sub"])
    # Syllabus.created_by = users.id (user_id), teacher.id emas
    data = await syl_svc.list_syllabuses(db, teacher_id=user_id)
    return ok(data)


@router.post("/teacher/syllabuses", status_code=201)
async def create_syllabus(
    body: SyllabusCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    user_id = uuid.UUID(tkn["sub"])
    data = await syl_svc.create_syllabus(
        db, title=body.title, created_by=user_id,
        description=body.description, subject=body.subject,
        xp_per_topic=body.xp_per_topic, color=body.color, icon=body.icon,
    )
    await db.commit()
    return ok(data)


@router.get("/teacher/syllabuses/{syllabus_id}")
async def get_syllabus(
    syllabus_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_teacher),
):
    data = await syl_svc.get_syllabus(db, syllabus_id)
    if not data:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "SYLLABUS_NOT_FOUND", "O'quv yo'li topilmadi")
    return ok(data)


@router.patch("/teacher/syllabuses/{syllabus_id}")
async def update_syllabus(
    syllabus_id: uuid.UUID,
    body: SyllabusUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_teacher),
):
    data = await syl_svc.update_syllabus(db, syllabus_id, **body.model_dump(exclude_none=True))
    await db.commit()
    return ok(data)


@router.delete("/teacher/syllabuses/{syllabus_id}", status_code=204)
async def delete_syllabus(
    syllabus_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_teacher),
):
    await syl_svc.delete_syllabus(db, syllabus_id)
    await db.commit()


# ── Topics ────────────────────────────────────────────────────────────

@router.post("/teacher/syllabuses/{syllabus_id}/topics", status_code=201)
async def add_topic(
    syllabus_id: uuid.UUID,
    body: TopicCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_teacher),
):
    data = await syl_svc.add_topic(
        db, syllabus_id=syllabus_id, title=body.title,
        description=body.description, xp_reward=body.xp_reward,
        order_index=body.order_index,
    )
    await db.commit()
    return ok(data)


@router.patch("/teacher/topics/{topic_id}")
async def update_topic(
    topic_id: uuid.UUID,
    body: TopicUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_teacher),
):
    data = await syl_svc.update_topic(db, topic_id, **body.model_dump(exclude_none=True))
    await db.commit()
    return ok(data)


@router.delete("/teacher/topics/{topic_id}", status_code=204)
async def delete_topic(
    topic_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_teacher),
):
    await syl_svc.delete_topic(db, topic_id)
    await db.commit()


@router.post("/teacher/syllabuses/{syllabus_id}/reorder")
async def reorder_topics(
    syllabus_id: uuid.UUID,
    body: ReorderTopics,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_teacher),
):
    data = await syl_svc.reorder_topics(db, syllabus_id, body.topic_ids)
    await db.commit()
    return ok(data)


# ── Assignments (biriktirish) ─────────────────────────────────────────

@router.post("/teacher/syllabuses/{syllabus_id}/assign")
async def assign_syllabus(
    syllabus_id: uuid.UUID,
    body: AssignRequest,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    user_id = uuid.UUID(tkn["sub"])
    data = await syl_svc.assign_syllabus(
        db, syllabus_id=syllabus_id,
        target_type=body.target_type,
        target_id=body.target_id,
        assigned_by=user_id,
    )
    await db.commit()
    return ok(data)


@router.delete("/teacher/syllabuses/{syllabus_id}/assign")
async def unassign_syllabus(
    syllabus_id: uuid.UUID,
    body: AssignRequest,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_teacher),
):
    await syl_svc.unassign_syllabus(
        db, syllabus_id=syllabus_id,
        target_type=body.target_type, target_id=body.target_id,
    )
    await db.commit()
    return ok({"removed": True})


# ── Mavzu bajarildi ───────────────────────────────────────────────────

@router.post("/teacher/topics/{topic_id}/complete")
async def complete_topic(
    topic_id: uuid.UUID,
    body: CompleteTopicRequest,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """Mavzuni bir yoki bir necha o'quvchi uchun bajarildi deb belgilash."""
    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)
    if not teacher:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(403, "NOT_TEACHER", "O'qituvchi topilmadi")

    results = await syl_svc.bulk_complete_topics(
        db, teacher_id=teacher.id,
        topic_id=topic_id,
        student_ids=body.student_ids,
    )
    return ok(results)


# ══════════════════════════════════════════════════════════════════════
# LEADERBOARD
# ══════════════════════════════════════════════════════════════════════

@router.get("/teacher/leaderboard")
async def get_leaderboard(
    group_id: Optional[uuid.UUID] = Query(None),
    period:   str                 = Query("weekly"),
    db:  AsyncSession             = Depends(get_tenant_session),
    tkn: dict                     = Depends(require_teacher),
):
    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)
    # O'qituvchining guruhlarini aniqlash uchun teacher.id ishlatamiz
    # group_id tanlansa — faqat o'sha guruh, aks holda barcha o'z guruhlari
    teacher_db_id = teacher.id if teacher else None
    data = await syl_svc.get_leaderboard(
        db,
        teacher_id=teacher_db_id,
        group_id=group_id,
        period=period,
    )
    # Guruhlar ro'yxatini ham qo'shamiz (filter uchun)
    from app.models.tenant.group import Group
    from sqlalchemy import select as sa_select
    if teacher_db_id:
        groups_rows = (await db.execute(
            sa_select(Group).where(Group.teacher_id == teacher_db_id, Group.status == "active")
        )).scalars().all()
        data["groups"] = [{"id": str(g.id), "name": g.name} for g in groups_rows]
    else:
        data["groups"] = []
    return ok(data)


# ══════════════════════════════════════════════════════════════════════
# BILDIRISHNOMALAR
# ══════════════════════════════════════════════════════════════════════

@router.get("/teacher/notifications")
async def get_notifications(
    is_read: Optional[bool]  = Query(None),
    page:    int             = Query(1, ge=1),
    per_page:int             = Query(20, ge=1, le=50),
    db:  AsyncSession        = Depends(get_tenant_session),
    tkn: dict                = Depends(require_teacher),
):
    user_id = uuid.UUID(tkn["sub"])
    stmt = select(Notification).where(Notification.user_id == user_id)
    if is_read is not None:
        stmt = stmt.where(Notification.is_read == is_read)
    stmt = stmt.order_by(Notification.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    rows  = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id)
    )).scalar_one()

    data = [{
        "id":         str(n.id),
        "type":       n.type,
        "title":      n.title,
        "body":       n.body,
        "data":       n.data or {},
        "is_read":    n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    } for n in rows]

    unread = (await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id, Notification.is_read == False)
    )).scalar_one()

    return ok(data, {"total": total, "unread": unread})


@router.post("/teacher/notifications/{notif_id}/read")
async def mark_read(
    notif_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    user_id = uuid.UUID(tkn["sub"])
    n = (await db.execute(
        select(Notification).where(
            Notification.id == notif_id, Notification.user_id == user_id
        )
    )).scalar_one_or_none()
    if n:
        n.is_read = True
        from datetime import datetime
        n.read_at = datetime.utcnow()
        await db.commit()
    return ok({"read": True})


@router.post("/teacher/notifications/read-all")
async def mark_all_read(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    from sqlalchemy import update as sql_update
    from datetime import datetime
    user_id = uuid.UUID(tkn["sub"])
    await db.execute(
        sql_update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True, read_at=datetime.utcnow())
    )
    await db.commit()
    return ok({"marked_all": True})


# ══════════════════════════════════════════════════════════════════════
# O'QUVCHI SO'ROVLARI (guruhga tayinlash)
# ══════════════════════════════════════════════════════════════════════

class AssignStudentRequest(BaseModel):
    student_id: uuid.UUID
    group_id:   uuid.UUID
    notes:      Optional[str] = None


@router.post("/teacher/requests/assign-student")
async def request_assign_student(
    body: AssignStudentRequest,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """O'quvchini guruhga tayinlash uchun inspektor/admin ga so'rov."""
    from app.models.tenant.branch_ops import InspectorRequest
    from sqlalchemy.dialects.postgresql import insert

    user_id = uuid.UUID(tkn["sub"])
    teacher = await _get_teacher(db, user_id)

    req = InspectorRequest(
        branch_id   = teacher.branch_id if teacher else None,
        requested_by= user_id,
        request_type= "assign_to_group",
        status      = "pending",
        notes       = body.notes or f"O'quvchini guruhga tayinlash so'rovi",
        extra_data  = {
            "student_id": str(body.student_id),
            "group_id":   str(body.group_id),
        },
    )
    db.add(req)
    await db.flush()

    # Admin + inspektorlarga notification
    admins = (await db.execute(
        select(User).where(
            User.role.in_(["admin", "inspector"]),
            User.is_active == True,
        )
    )).scalars().all()

    for admin in admins:
        db.add(Notification(
            user_id = admin.id,
            type    = "assign_request",
            title   = "Yangi tayinlash so'rovi",
            body    = f"O'qituvchi o'quvchini guruhga tayinlash so'radi",
            data    = {"request_id": str(req.id)},
            channel = "telegram",
        ))

    # O'qituvchiga o'ziga ham
    db.add(Notification(
        user_id = user_id,
        type    = "request_sent",
        title   = "So'rov yuborildi",
        body    = "O'quvchini guruhga tayinlash so'rovingiz yuborildi. Inspektor tasdiqlashini kuting.",
        data    = {"request_id": str(req.id)},
        channel = "telegram",
    ))

    await db.commit()
    return ok({"request_id": str(req.id), "status": "pending"})


@router.get("/teacher/requests")
async def my_requests(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_teacher),
):
    """O'qituvchining yuborgan so'rovlari."""
    from app.models.tenant.branch_ops import InspectorRequest
    user_id = uuid.UUID(tkn["sub"])
    rows = (await db.execute(
        select(InspectorRequest)
        .where(InspectorRequest.requested_by == user_id)
        .order_by(InspectorRequest.created_at.desc())
        .limit(30)
    )).scalars().all()

    data = [{
        "id":           str(r.id),
        "type":         r.request_type,
        "status":       r.status,
        "notes":        r.notes,
        "extra_data":   r.extra_data or {},
        "created_at":   r.created_at.isoformat() if r.created_at else None,
        "reviewed_at":  r.reviewed_at.isoformat() if r.reviewed_at else None,
        "reject_reason":r.reject_reason,
    } for r in rows]
    return ok(data)
