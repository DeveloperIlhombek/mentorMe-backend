"""
app/api/v1/admin/attendance.py

Davomat endpointlari.
O'qituvchi va admin foydalanadi.
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_inspector, require_teacher, get_optional_branch_filter
from app.models.tenant import Teacher, Attendance
from app.schemas import AttendanceBulkCreate, ok
from app.services import attendance as att_svc

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("", status_code=201)
async def create_attendance(
    data: AttendanceBulkCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_teacher),
):
    """
    Bulk davomat kiritish — bir guruh, bir kun.
    O'qituvchi ID avtomatik aniqlanadi.
    """
    # O'qituvchini user_id orqali topish
    teacher_stmt = select(Teacher).where(
        Teacher.user_id == uuid.UUID(tkn["sub"])
    )
    teacher = (await db.execute(teacher_stmt)).scalar_one_or_none()
    teacher_id = teacher.id if teacher else None

    result = await att_svc.bulk_create(db, data, teacher_id)
    return ok(result)


@router.get("")
async def get_attendance(
    group_id: Optional[uuid.UUID] = Query(None),
    date_val: Optional[date]      = Query(None, alias="date"),
    db: AsyncSession               = Depends(get_tenant_session),
    _:  dict                       = Depends(require_teacher),
    branch_filter: Optional[str]   = Depends(get_optional_branch_filter),
):
    """Guruhning ma'lum kkundagi davomati."""
    if group_id and date_val:
        # Inspektor bo'lsa — guruh uning fililiga tegishli ekanligini tekshir
        if branch_filter:
            from sqlalchemy import select as _sel
            from app.models.tenant.group import Group as _Group
            import uuid as _uuid
            grp = (await db.execute(
                _sel(_Group).where(_Group.id == group_id)
            )).scalar_one_or_none()
            if not grp or str(grp.branch_id) != branch_filter:
                return ok([])
        records = await att_svc.get_by_group_date(db, group_id, date_val)
        return ok(records)
    return ok([])


@router.get("/summary")
async def get_summary(
    group_id: uuid.UUID,
    date_val: date = Query(..., alias="date"),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """Guruhning bir kundagi statistikasi (present/absent/late/excused)."""
    summary = await att_svc.get_summary(db, group_id, date_val)
    return ok(summary)


@router.get("/weekly-stats")
async def get_weekly_stats(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
    branch_filter: Optional[str] = Depends(get_optional_branch_filter),
):
    """
    Dashboard uchun: oxirgi 7 kunlik davomat statistikasi.

    Denominator: o'sha kuni dars bo'lgan guruhlardagi BARCHA o'quvchilar soni.
    Bu formula: 'darsga kelishi kerak bo'lganlardan necha foizi keldi'.
    """
    from datetime import date, timedelta
    import uuid as _uuid

    today = date.today()
    days  = [(today - timedelta(days=i)) for i in range(6, -1, -1)]

    branch_uuid = _uuid.UUID(branch_filter) if branch_filter else None

    result = []
    for d in days:
        stats = await att_svc.get_stats_for_date(db, d, branch_id=branch_uuid)
        result.append({
            "date":              d.isoformat(),
            "day":               ["Du","Se","Ch","Pa","Ju","Sh","Ya"][d.weekday()],
            "expected":          stats["expected"],
            "present":           stats["present"],
            "late":              stats["late"],
            "absent":            stats["absent"],
            "pct":               stats["pct"],
            "groups_with_class": stats["groups_with_class"],
            "groups_marked":     stats["groups_marked"],
        })

    # avg_pct: faqat dars bo'lgan kunlar bo'yicha hisoblash
    days_with_class = [r for r in result if r["expected"] > 0]
    avg_pct = round(
        sum(r["pct"] for r in days_with_class) / len(days_with_class)
    ) if days_with_class else 0

    return ok({"days": result, "avg_pct": avg_pct})


@router.get("/today-groups")
async def get_today_groups(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
    branch_filter: Optional[str] = Depends(get_optional_branch_filter),
):
    """
    Bugun dars bo'lgan faol guruhlar ro'yxati.
    Inspektor uchun faqat o'z filiali guruhlari.
    """
    from datetime import date as _date
    from app.models.tenant.group import Group
    import uuid as _uuid

    today_dow = _date.today().isoweekday()  # 1=Du...7=Ya

    stmt = (
        select(Group)
        .where(Group.status == "active")
        .order_by(Group.name)
    )
    if branch_filter:
        stmt = stmt.where(Group.branch_id == _uuid.UUID(branch_filter))
    all_groups = (await db.execute(stmt)).scalars().all()

    result = []
    for g in all_groups:
        schedule = g.schedule or []
        # JSONB list ichida bugungi kun bormi?
        today_slots = [s for s in schedule if s.get("day") == today_dow]
        if today_slots:
            result.append({
                "id":           str(g.id),
                "name":         g.name,
                "subject":      g.subject,
                "level":        g.level,
                "monthly_fee":  float(g.monthly_fee) if g.monthly_fee else None,
                "max_students": g.max_students,
                "today_slots":  today_slots,   # [{start, end, room}]
                "first_slot":   today_slots[0].get("start", ""),
            })

    # Dars vaqti bo'yicha tartiblash
    result.sort(key=lambda x: x["first_slot"])

    return ok(result, {"total": len(result), "weekday": today_dow})
