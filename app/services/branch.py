"""app/services/branch.py — Filial biznes logikasi."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.branch import Branch
from app.models.tenant.branch_ops import BranchExpense, InspectorRequest
from app.models.tenant.user import User
from app.models.tenant.student import Student
from app.models.tenant.teacher import Teacher
from app.models.tenant.group import Group
from app.models.tenant.payment import Payment
from app.models.tenant.attendance import Attendance


# ─── Filiallar CRUD ───────────────────────────────────────────────────

async def get_branches(
    db:          AsyncSession,
    active_only: bool = True,
) -> List[dict]:
    stmt = select(Branch)
    if active_only:
        stmt = stmt.where(Branch.is_active == True)
    stmt = stmt.order_by(Branch.is_main.desc(), Branch.name)
    rows = (await db.execute(stmt)).scalars().all()
    result = []
    for b in rows:
        result.append(await _branch_dict(db, b))
    return result


async def get_branch(db: AsyncSession, branch_id: uuid.UUID) -> Optional[dict]:
    b = (await db.execute(
        select(Branch).where(Branch.id == branch_id)
    )).scalar_one_or_none()
    if not b:
        return None
    return await _branch_dict(db, b, detailed=True)


async def create_branch(
    db:         AsyncSession,
    name:       str,
    address:    Optional[str] = None,
    phone:      Optional[str] = None,
    manager_id: Optional[uuid.UUID] = None,
    is_main:    bool = False,
) -> dict:
    # Faqat bitta asosiy filial bo'lishi mumkin
    if is_main:
        await db.execute(
            select(Branch)  # update all is_main to False
        )
        existing_main = (await db.execute(
            select(Branch).where(Branch.is_main == True)
        )).scalars().all()
        for em in existing_main:
            em.is_main = False

    b = Branch(
        name=name, address=address, phone=phone,
        manager_id=manager_id, is_main=is_main,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return await _branch_dict(db, b)


async def update_branch(
    db:        AsyncSession,
    branch_id: uuid.UUID,
    **kwargs,
) -> dict:
    b = (await db.execute(
        select(Branch).where(Branch.id == branch_id)
    )).scalar_one_or_none()
    if not b:
        raise ValueError("Filial topilmadi")
    for k, v in kwargs.items():
        if hasattr(b, k) and v is not None:
            setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return await _branch_dict(db, b)


async def delete_branch(db: AsyncSession, branch_id: uuid.UUID) -> None:
    b = (await db.execute(
        select(Branch).where(Branch.id == branch_id)
    )).scalar_one_or_none()
    if b:
        b.is_active = False
        await db.commit()


async def assign_inspector(
    db:          AsyncSession,
    branch_id:   uuid.UUID,
    user_id:     uuid.UUID,
) -> dict:
    """Foydalanuvchini inspektor sifatida filiaga tayinlash."""
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise ValueError("Foydalanuvchi topilmadi")

    branch = (await db.execute(
        select(Branch).where(Branch.id == branch_id)
    )).scalar_one_or_none()
    if not branch:
        raise ValueError("Filial topilmadi")

    user.role      = "inspector"
    user.branch_id = branch_id
    branch.manager_id = user_id
    await db.commit()
    return {"user_id": str(user_id), "branch_id": str(branch_id), "role": "inspector"}


async def remove_inspector(
    db:        AsyncSession,
    branch_id: uuid.UUID,
) -> None:
    """Filialdan inspektor olib tashlash."""
    branch = (await db.execute(
        select(Branch).where(Branch.id == branch_id)
    )).scalar_one_or_none()
    if not branch or not branch.manager_id:
        return

    user = (await db.execute(
        select(User).where(User.id == branch.manager_id)
    )).scalar_one_or_none()
    if user:
        user.role      = "teacher"   # yoki admin belgilaydi
        user.branch_id = None

    branch.manager_id = None
    await db.commit()


# ─── Filial statistika ────────────────────────────────────────────────

async def get_branch_stats(
    db:        AsyncSession,
    branch_id: uuid.UUID,
    month:     Optional[int] = None,
    year:      Optional[int] = None,
) -> dict:
    from datetime import date
    today = date.today()
    m = month or today.month
    y = year  or today.year

    student_count = (await db.execute(
        select(func.count(Student.id)).where(
            Student.branch_id == branch_id,
            Student.is_active == True,
        )
    )).scalar_one()

    teacher_count = (await db.execute(
        select(func.count(Teacher.id)).where(
            Teacher.branch_id == branch_id,
            Teacher.is_active == True,
        )
    )).scalar_one()

    group_count = (await db.execute(
        select(func.count(Group.id)).where(
            Group.branch_id == branch_id,
            Group.status    == "active",
        )
    )).scalar_one()

    # Oylik kirim
    income = (await db.execute(
        select(func.sum(Payment.amount)).where(
            and_(
                Payment.status       == "completed",
                Payment.period_month == m,
                Payment.period_year  == y,
            )
        ).join(Student, Payment.student_id == Student.id)
        .where(Student.branch_id == branch_id)
    )).scalar_one() or 0

    # Tasdiqlangan xarajatlar
    expenses = (await db.execute(
        select(func.sum(BranchExpense.amount)).where(
            BranchExpense.branch_id == branch_id,
            BranchExpense.status    == "approved",
        )
    )).scalar_one() or 0

    return {
        "branch_id":     str(branch_id),
        "month":         m,
        "year":          y,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "group_count":   group_count,
        "income":        float(income),
        "expenses":      float(expenses),
        "net":           float(income) - float(expenses),
    }


async def get_branch_dashboard(
    db:        AsyncSession,
    branch_id: uuid.UUID,
    month:     Optional[int] = None,
    year:      Optional[int] = None,
) -> dict:
    """Filial uchun to'liq dashboard ma'lumotlari."""
    from datetime import date, timedelta

    today = date.today()
    m = month or today.month
    y = year  or today.year

    # ── Asosiy hisoblar ────────────────────────────────────────────
    student_count = (await db.execute(
        select(func.count(Student.id)).where(
            Student.branch_id == branch_id,
            Student.is_active == True,
        )
    )).scalar_one()

    teacher_count = (await db.execute(
        select(func.count(Teacher.id)).where(
            Teacher.branch_id == branch_id,
            Teacher.is_active == True,
        )
    )).scalar_one()

    group_count = (await db.execute(
        select(func.count(Group.id)).where(
            Group.branch_id == branch_id,
            Group.status    == "active",
        )
    )).scalar_one()

    # ── Moliya ─────────────────────────────────────────────────────
    # Oylik kirim (to'lovlar)
    income = (await db.execute(
        select(func.sum(Payment.amount))
        .join(Student, Payment.student_id == Student.id)
        .where(
            Student.branch_id    == branch_id,
            Payment.status       == "completed",
            Payment.period_month == m,
            Payment.period_year  == y,
        )
    )).scalar_one() or Decimal("0")

    # Qarzdorlar (manfiy balans)
    debt_count = (await db.execute(
        select(func.count(Student.id)).where(
            Student.branch_id == branch_id,
            Student.is_active == True,
            Student.balance   <  0,
        )
    )).scalar_one()

    total_debt = (await db.execute(
        select(func.sum(Student.balance)).where(
            Student.branch_id == branch_id,
            Student.is_active == True,
            Student.balance   <  0,
        )
    )).scalar_one() or Decimal("0")

    # Oylik xarajatlar
    expenses = (await db.execute(
        select(func.sum(BranchExpense.amount)).where(
            BranchExpense.branch_id == branch_id,
            BranchExpense.status    == "approved",
        )
    )).scalar_one() or Decimal("0")

    # O'qituvchilar maoshi (oy)
    teacher_salary = (await db.execute(
        select(func.sum(Teacher.salary_amount)).where(
            Teacher.branch_id == branch_id,
            Teacher.is_active == True,
            Teacher.salary_type == "fixed",
        )
    )).scalar_one() or Decimal("0")

    # ── Haftalik davomat trend ─────────────────────────────────────
    weekly_trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        row = (await db.execute(
            select(
                func.count(Attendance.id).label("total"),
                func.count(
                    Attendance.id if True else None
                ).filter(Attendance.status.in_(["present","late"])).label("present"),
            )
            .join(Student, Attendance.student_id == Student.id)
            .where(
                Student.branch_id == branch_id,
                Attendance.date   == d,
            )
        )).first()
        total   = row.total   if row else 0
        present = row.present if row else 0
        weekly_trend.append({
            "date":    d.isoformat(),
            "weekday": d.strftime("%a"),
            "total":   total,
            "present": present,
            "pct":     round(present / total * 100, 1) if total else 0,
        })

    # ── Oxirgi to'lovlar (5 ta) ────────────────────────────────────
    recent_payments_rows = (await db.execute(
        select(Payment, Student, User)
        .join(Student, Payment.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(
            Student.branch_id == branch_id,
            Payment.status    == "completed",
        )
        .order_by(desc(Payment.created_at))
        .limit(5)
    )).all()

    recent_payments = [{
        "student_name":   f"{u.first_name} {u.last_name or ''}".strip(),
        "amount":         float(p.amount),
        "payment_method": p.payment_method,
        "paid_at":        p.paid_at.isoformat() if p.paid_at else p.created_at.isoformat(),
    } for p, s, u in recent_payments_rows]

    # ── Yangi o'quvchilar (bu oy) ──────────────────────────────────
    from sqlalchemy import extract
    new_students_rows = (await db.execute(
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(
            Student.branch_id == branch_id,
            Student.is_active == True,
            extract("month", Student.enrolled_at) == m,
            extract("year",  Student.enrolled_at) == y,
        )
        .order_by(desc(Student.enrolled_at))
        .limit(5)
    )).all()

    new_students = [{
        "id":         str(s.id),
        "name":       f"{u.first_name} {u.last_name or ''}".strip(),
        "phone":      u.phone,
        "enrolled_at":s.enrolled_at.isoformat() if s.enrolled_at else None,
    } for s, u in new_students_rows]

    # ── Bugungi guruhlar ───────────────────────────────────────────
    today_dow = today.isoweekday()
    groups_rows = (await db.execute(
        select(Group)
        .where(Group.branch_id == branch_id, Group.status == "active")
        .order_by(Group.name)
    )).scalars().all()

    today_groups = []
    for g in groups_rows:
        schedule = g.schedule or []
        slots = [s for s in schedule if s.get("day") == today_dow]
        if slots:
            today_groups.append({
                "id":      str(g.id),
                "name":    g.name,
                "subject": g.subject,
                "slots":   slots,
                "start":   slots[0].get("start",""),
            })
    today_groups.sort(key=lambda x: x["start"])

    # ── Kutilayotgan so'rovlar ─────────────────────────────────────
    pending_requests = (await db.execute(
        select(func.count(InspectorRequest.id)).where(
            InspectorRequest.branch_id == branch_id,
            InspectorRequest.status    == "pending",
        )
    )).scalar_one()

    pending_expenses = (await db.execute(
        select(func.count(BranchExpense.id)).where(
            BranchExpense.branch_id == branch_id,
            BranchExpense.status    == "pending",
        )
    )).scalar_one()

    # ── Oxirgi davomat ─────────────────────────────────────────────
    recent_attendance = (await db.execute(
        select(
            func.count(Attendance.id).label("total"),
            func.count(Attendance.id).filter(
                Attendance.status.in_(["present","late"])
            ).label("present"),
            func.count(Attendance.id).filter(
                Attendance.status == "absent"
            ).label("absent"),
        )
        .join(Student, Attendance.student_id == Student.id)
        .where(
            Student.branch_id == branch_id,
            Attendance.date   == today,
        )
    )).first()

    today_att = {
        "total":   recent_attendance.total   if recent_attendance else 0,
        "present": recent_attendance.present if recent_attendance else 0,
        "absent":  recent_attendance.absent  if recent_attendance else 0,
        "pct":     round(
            recent_attendance.present / recent_attendance.total * 100, 1
        ) if recent_attendance and recent_attendance.total else 0,
    }

    return {
        "branch_id":     str(branch_id),
        "period":        {"month": m, "year": y},
        "summary": {
            "student_count": student_count,
            "teacher_count": teacher_count,
            "group_count":   group_count,
            "debt_count":    debt_count,
        },
        "finance": {
            "income":          float(income),
            "expenses":        float(expenses),
            "teacher_salary":  float(teacher_salary),
            "total_debt":      float(total_debt),
            "net":             float(income) - float(expenses) - float(teacher_salary),
        },
        "today_attendance":  today_att,
        "weekly_trend":      weekly_trend,
        "today_groups":      today_groups,
        "recent_payments":   recent_payments,
        "new_students":      new_students,
        "pending_requests":  pending_requests,
        "pending_expenses":  pending_expenses,
    }


# ─── Xarajatlar ───────────────────────────────────────────────────────

async def get_expenses(
    db:        AsyncSession,
    branch_id: Optional[uuid.UUID] = None,
    status:    Optional[str]       = None,
) -> List[dict]:
    stmt = select(BranchExpense, User, Branch)\
        .join(User,   BranchExpense.requested_by == User.id, isouter=True)\
        .join(Branch, BranchExpense.branch_id    == Branch.id)\
        .order_by(desc(BranchExpense.created_at))
    if branch_id:
        stmt = stmt.where(BranchExpense.branch_id == branch_id)
    if status:
        stmt = stmt.where(BranchExpense.status == status)
    rows = (await db.execute(stmt)).all()
    return [_expense_dict(e, u, b) for e, u, b in rows]


async def create_expense_request(
    db:           AsyncSession,
    branch_id:    uuid.UUID,
    requested_by: uuid.UUID,
    title:        str,
    amount:       float,
    category:     Optional[str] = None,
    description:  Optional[str] = None,
) -> dict:
    e = BranchExpense(
        branch_id    = branch_id,
        requested_by = requested_by,
        title        = title,
        amount       = Decimal(str(amount)),
        category     = category,
        description  = description,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return {"id": str(e.id), "status": e.status, "title": e.title, "amount": float(e.amount)}


async def review_expense(
    db:          AsyncSession,
    expense_id:  uuid.UUID,
    admin_id:    uuid.UUID,
    approve:     bool,
    reason:      Optional[str] = None,
) -> dict:
    e = (await db.execute(
        select(BranchExpense).where(BranchExpense.id == expense_id)
    )).scalar_one_or_none()
    if not e:
        raise ValueError("Xarajat topilmadi")

    e.approved_by = admin_id
    e.status      = "approved" if approve else "rejected"
    e.approved_at = datetime.utcnow()
    if not approve and reason:
        e.rejected_reason = reason
    await db.commit()
    return {"id": str(e.id), "status": e.status}


# ─── Inspektor so'rovlari ─────────────────────────────────────────────

async def get_inspector_requests(
    db:        AsyncSession,
    branch_id: Optional[uuid.UUID] = None,
    status:    Optional[str]       = None,
) -> List[dict]:
    stmt = select(InspectorRequest, User, Branch)\
        .join(User,   InspectorRequest.inspector_id == User.id, isouter=True)\
        .join(Branch, InspectorRequest.branch_id    == Branch.id)\
        .order_by(desc(InspectorRequest.created_at))
    if branch_id:
        stmt = stmt.where(InspectorRequest.branch_id == branch_id)
    if status:
        stmt = stmt.where(InspectorRequest.status == status)
    rows = (await db.execute(stmt)).all()
    return [_request_dict(r, u, b) for r, u, b in rows]


async def create_teacher_request(
    db:           AsyncSession,
    branch_id:    uuid.UUID,
    inspector_id: uuid.UUID,
    first_name:   str,
    last_name:    Optional[str],
    phone:        Optional[str],
    subjects:     Optional[str],
    salary_type:  Optional[str],
    salary_amount: Optional[float],
    notes:        Optional[str] = None,
) -> dict:
    req = InspectorRequest(
        branch_id    = branch_id,
        inspector_id = inspector_id,
        request_type = "add_teacher",
        first_name   = first_name,
        last_name    = last_name,
        phone        = phone,
        subjects     = subjects,
        salary_type  = salary_type,
        salary_amount= Decimal(str(salary_amount)) if salary_amount else None,
        notes        = notes,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return _request_dict(req, None, None)


async def review_teacher_request(
    db:         AsyncSession,
    request_id: uuid.UUID,
    admin_id:   uuid.UUID,
    approve:    bool,
    reason:     Optional[str] = None,
) -> dict:
    """Admin inspektorning o'qituvchi so'rovini ko'rib chiqadi."""
    from app.models.tenant.teacher import Teacher

    req = (await db.execute(
        select(InspectorRequest).where(InspectorRequest.id == request_id)
    )).scalar_one_or_none()
    if not req:
        raise ValueError("So'rov topilmadi")

    req.reviewed_by = admin_id
    req.reviewed_at = datetime.utcnow()

    if approve:
        req.status = "approved"
        try:
            subjects_list = [s.strip() for s in req.subjects.split(",")] if req.subjects else []

            # User yaratish
            from app.core.security import hash_password
            new_user = User(
                first_name    = req.first_name,
                last_name     = req.last_name,
                phone         = req.phone,
                role          = "teacher",
                branch_id     = req.branch_id,
                password_hash = hash_password("Teacher123!"),
                is_active     = True,
                is_verified   = True,
            )
            db.add(new_user)
            await db.flush()

            # Teacher yaratish
            new_teacher = Teacher(
                user_id       = new_user.id,
                branch_id     = req.branch_id,
                subjects      = subjects_list,
                salary_type   = req.salary_type,
                salary_amount = Decimal(str(req.salary_amount)) if req.salary_amount else None,
                is_active     = True,
            )
            db.add(new_teacher)
            await db.flush()

            req.created_teacher_id = new_teacher.id

        except Exception as e:
            req.status        = "rejected"
            req.reject_reason = f"O'qituvchi yaratishda xato: {e}"
    else:
        req.status        = "rejected"
        req.reject_reason = reason

    await db.commit()
    return {
        "id":         str(req.id),
        "status":     req.status,
        "teacher_id": str(req.created_teacher_id) if req.created_teacher_id else None,
    }


# ─── Helpers ─────────────────────────────────────────────────────────

async def _branch_dict(
    db:       AsyncSession,
    b:        Branch,
    detailed: bool = False,
) -> dict:
    manager_name = None
    if b.manager_id:
        mgr = (await db.execute(
            select(User).where(User.id == b.manager_id)
        )).scalar_one_or_none()
        if mgr:
            manager_name = f"{mgr.first_name} {mgr.last_name or ''}".strip()

    result = {
        "id":           str(b.id),
        "name":         b.name,
        "address":      b.address,
        "phone":        b.phone,
        "is_main":      b.is_main,
        "is_active":    b.is_active,
        "manager_id":   str(b.manager_id) if b.manager_id else None,
        "manager_name": manager_name,
    }

    if detailed:
        stats = await get_branch_stats(db, b.id)
        result.update({
            "student_count": stats["student_count"],
            "teacher_count": stats["teacher_count"],
            "group_count":   stats["group_count"],
        })

    return result


def _expense_dict(e: BranchExpense, u, b) -> dict:
    return {
        "id":              str(e.id),
        "branch_id":       str(e.branch_id),
        "branch_name":     b.name if b else None,
        "requested_by_id": str(e.requested_by) if e.requested_by else None,
        "requested_by":    f"{u.first_name} {u.last_name or ''}".strip() if u else None,
        "title":           e.title,
        "description":     e.description,
        "amount":          float(e.amount),
        "category":        e.category,
        "status":          e.status,
        "rejected_reason": e.rejected_reason,
        "approved_at":     e.approved_at.isoformat() if e.approved_at else None,
        "created_at":      e.created_at.isoformat() if e.created_at else None,
    }


def _request_dict(r: InspectorRequest, u, b) -> dict:
    return {
        "id":           str(r.id),
        "branch_id":    str(r.branch_id),
        "branch_name":  b.name if b else None,
        "inspector":    f"{u.first_name} {u.last_name or ''}".strip() if u else None,
        "request_type": r.request_type,
        "first_name":   r.first_name,
        "last_name":    r.last_name,
        "phone":        r.phone,
        "subjects":     r.subjects,
        "salary_type":  r.salary_type,
        "salary_amount":float(r.salary_amount) if r.salary_amount else None,
        "notes":        r.notes,
        "status":       r.status,
        "reject_reason":r.reject_reason,
        "reviewed_at":  r.reviewed_at.isoformat() if r.reviewed_at else None,
        "created_teacher_id": str(r.created_teacher_id) if r.created_teacher_id else None,
        "created_at":   r.created_at.isoformat() if r.created_at else None,
    }
