"""
app/services/payment.py

To'lovlar: naqd qo'shish, ro'yxat, qarzdorlar.
Click webhook alohida: app/webhooks/click.py da.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StudentNotFound
from app.models.tenant import Group, Payment, Student, StudentGroup, User
from app.schemas.payment import PaymentCreate


async def get_payments(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    student_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    branch_id: Optional[uuid.UUID] = None,
) -> Tuple[List[dict], int]:
    """To'lovlar ro'yxati (filter, sahifalash)."""
    stmt = select(Payment)

    if student_id: stmt = stmt.where(Payment.student_id == student_id)
    if status:     stmt = stmt.where(Payment.status == status)
    if month:      stmt = stmt.where(Payment.period_month == month)
    if year:       stmt = stmt.where(Payment.period_year == year)
    if branch_id:
        stmt = stmt.join(Student, Payment.student_id == Student.id)                   .where(Student.branch_id == branch_id)

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    stmt = (
        stmt
        .order_by(Payment.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    payments = (await db.execute(stmt)).scalars().all()

    result = []
    for p in payments:
        student_data = await _student_short(db, p.student_id)
        # student_name — dashboard uchun flat field
        sname = ""
        if student_data:
            sname = f"{student_data.get('first_name', '')} {student_data.get('last_name', '') or ''}".strip()

        result.append({
            "id": str(p.id),
            "student_id": str(p.student_id),
            "student_name": sname,
            "first_name": student_data.get("first_name") if student_data else None,
            "last_name":  student_data.get("last_name")  if student_data else None,
            "amount": float(p.amount),
            "currency": p.currency,
            "payment_type": p.payment_type,
            "payment_method": p.payment_method,
            "status": p.status,
            "period_month": p.period_month,
            "period_year": p.period_year,
            "note": p.note,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "created_at": p.created_at.isoformat(),
            "student": student_data,
        })

    return result, total


async def create_manual(
    db: AsyncSession,
    data: PaymentCreate,
    received_by: uuid.UUID,
) -> dict:
    """
    Naqd to'lov qo'shish (admin tomonidan qo'lda).
    Student balansi avtomatik yangilanadi.
    """
    # Student mavjudligini tekshirish
    stmt = select(Student).where(Student.id == data.student_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        raise StudentNotFound()

    # To'lov yozuvi
    payment = Payment(
        student_id=data.student_id,
        group_id=data.group_id,
        amount=data.amount,
        payment_method=data.payment_method,
        payment_type=data.payment_type,
        period_month=data.period_month,
        period_year=data.period_year,
        note=data.note,
        status="completed",
        received_by=received_by,
        paid_at=datetime.utcnow(),
    )
    db.add(payment)

    # Balans yangilash
    student.balance = float(student.balance) + data.amount

    # Moliya: avtomatik kirim yozuvi
    try:
        from app.services.finance import create_transaction
        from decimal import Decimal
        await create_transaction(
            db,
            type           = "income",
            amount         = Decimal(str(data.amount)),
            category       = "talaba_tolov",
            payment_method = "cash" if data.payment_method == "cash" else "bank",
            description    = "O'quvchi to'lovi",
            reference_type = "payment",
            reference_id   = payment.id,
            created_by     = received_by,
        )
    except Exception:
        pass  # Moliya moduli ishlamasa asosiy to'lov baribir saqlanadi

    await db.commit()
    return {
        "id": str(payment.id),
        "amount": float(payment.amount),
        "status": "completed",
        "new_balance": float(student.balance),
    }


async def get_debtors(db: AsyncSession) -> List[dict]:
    """
    Manfiy balansli (qarzdor) faol o'quvchilar.
    Eng ko'p qarzdan boshlab tartiblangan.
    """
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(
            and_(
                Student.balance < 0,
                Student.is_active == True,
            )
        )
        .order_by(Student.balance)  # Eng katta qarz birinchi
    )
    rows = (await db.execute(stmt)).all()

    result = []
    for st, u in rows:
        groups = await _student_groups_short(db, st.id)
        result.append({
            "id": str(st.id),
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": u.phone,
            "balance": float(st.balance),
            "groups": groups,
        })
    return result


# ─── yordamchi ───────────────────────────────────────────────────────

async def _student_short(db: AsyncSession, student_id: uuid.UUID) -> Optional[dict]:
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.id == student_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    st, u = row
    return {
        "id": str(st.id),
        "first_name": u.first_name,
        "last_name": u.last_name,
        "balance": float(st.balance),
    }


async def _student_groups_short(db: AsyncSession, student_id: uuid.UUID) -> list:
    stmt = (
        select(Group.name, Group.monthly_fee)
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
        {"name": name, "monthly_fee": float(fee) if fee else None}
        for name, fee in rows
    ]
