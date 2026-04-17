"""app/services/kpi.py — KPI hisoblash va boshqaruv."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.kpi import KpiMetric, KpiPayslip, KpiResult, KpiRule
from app.models.tenant.teacher import Teacher
from app.models.tenant.attendance import Attendance
from app.models.tenant.group import Group


# ─── Metrikalar CRUD ─────────────────────────────────────────────────

async def get_metrics(db: AsyncSession) -> List[dict]:
    rows = (await db.execute(
        select(KpiMetric).where(KpiMetric.is_active == True).order_by(KpiMetric.name)
    )).scalars().all()
    return [_metric_dict(m) for m in rows]


async def create_metric(
    db: AsyncSession,
    slug: str, name: str,
    metric_type: str = "percentage",
    direction: str   = "higher_better",
    unit: str        = "%",
    description: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
) -> dict:
    m = KpiMetric(
        slug=slug, name=name, metric_type=metric_type,
        direction=direction, unit=unit, description=description,
        created_by=created_by,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _metric_dict(m)


async def update_metric(
    db: AsyncSession, metric_id: uuid.UUID, **kwargs
) -> dict:
    m = (await db.execute(
        select(KpiMetric).where(KpiMetric.id == metric_id)
    )).scalar_one_or_none()
    if not m:
        raise ValueError("Metrika topilmadi")
    for k, v in kwargs.items():
        if hasattr(m, k) and v is not None:
            setattr(m, k, v)
    await db.commit()
    await db.refresh(m)
    return _metric_dict(m)


async def delete_metric(db: AsyncSession, metric_id: uuid.UUID) -> None:
    m = (await db.execute(
        select(KpiMetric).where(KpiMetric.id == metric_id)
    )).scalar_one_or_none()
    if m:
        m.is_active = False
        await db.commit()


# ─── Qoidalar CRUD ───────────────────────────────────────────────────

async def get_rules(
    db: AsyncSession, metric_id: Optional[uuid.UUID] = None
) -> List[dict]:
    stmt = select(KpiRule).order_by(KpiRule.threshold_min)
    if metric_id:
        stmt = stmt.where(KpiRule.metric_id == metric_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_rule_dict(r) for r in rows]


async def create_rule(
    db: AsyncSession,
    metric_id: uuid.UUID,
    reward_type: str,
    reward_value: Decimal,
    threshold_min: Optional[Decimal] = None,
    threshold_max: Optional[Decimal] = None,
    label: Optional[str] = None,
    period: str = "monthly",
) -> dict:
    r = KpiRule(
        metric_id=metric_id,
        threshold_min=threshold_min,
        threshold_max=threshold_max,
        reward_type=reward_type,
        reward_value=reward_value,
        label=label,
        period=period,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return _rule_dict(r)


async def delete_rule(db: AsyncSession, rule_id: uuid.UUID) -> None:
    r = (await db.execute(
        select(KpiRule).where(KpiRule.id == rule_id)
    )).scalar_one_or_none()
    if r:
        await db.delete(r)
        await db.commit()


# ─── KPI hisoblash ───────────────────────────────────────────────────

async def calculate_for_teacher(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    month: int,
    year: int,
) -> dict:
    """
    Bir o'qituvchi uchun berilgan oy KPI ni hisoblaydi:
    1. Har aktiv metrika uchun actual_value oladi
    2. Tegishli qoidani topadi
    3. reward_amount hisoblaydi
    4. kpi_results ga yozadi (upsert)
    5. kpi_payslips yaratadi/yangilaydi
    """
    teacher = (await db.execute(
        select(Teacher).where(Teacher.id == teacher_id)
    )).scalar_one_or_none()
    if not teacher:
        raise ValueError("O'qituvchi topilmadi")

    metrics = (await db.execute(
        select(KpiMetric).where(KpiMetric.is_active == True)
    )).scalars().all()

    results = []
    total_bonus   = Decimal("0")
    total_penalty = Decimal("0")

    for metric in metrics:
        actual = await _compute_metric(db, teacher_id, metric, month, year)
        rule   = await _find_matching_rule(db, metric.id, actual)
        reward = _compute_reward(rule, teacher.salary_amount, actual) if rule else Decimal("0")

        # Upsert kpi_results
        existing = (await db.execute(
            select(KpiResult).where(
                KpiResult.teacher_id   == teacher_id,
                KpiResult.metric_id    == metric.id,
                KpiResult.period_month == month,
                KpiResult.period_year  == year,
            )
        )).scalar_one_or_none()

        if existing:
            existing.actual_value  = actual
            existing.rule_id       = rule.id if rule else None
            existing.reward_amount = reward
            existing.calculated_at = datetime.utcnow()
        else:
            db.add(KpiResult(
                teacher_id    = teacher_id,
                metric_id     = metric.id,
                period_month  = month,
                period_year   = year,
                actual_value  = actual,
                rule_id       = rule.id if rule else None,
                reward_amount = reward,
            ))

        if reward > 0:
            total_bonus += reward
        elif reward < 0:
            total_penalty += abs(reward)

        results.append({
            "metric_slug":   metric.slug,
            "metric_name":   metric.name,
            "actual_value":  float(actual) if actual is not None else None,
            "rule_label":    rule.label if rule else None,
            "reward_amount": float(reward),
        })

    # Payslip upsert
    base = Decimal(str(teacher.salary_amount or 0))
    net  = base + total_bonus - total_penalty

    existing_slip = (await db.execute(
        select(KpiPayslip).where(
            KpiPayslip.teacher_id   == teacher_id,
            KpiPayslip.period_month == month,
            KpiPayslip.period_year  == year,
        )
    )).scalar_one_or_none()

    if existing_slip:
        existing_slip.total_bonus   = total_bonus
        existing_slip.total_penalty = total_penalty
        existing_slip.net_salary    = net
    else:
        db.add(KpiPayslip(
            teacher_id    = teacher_id,
            period_month  = month,
            period_year   = year,
            base_salary   = base,
            total_bonus   = total_bonus,
            total_penalty = total_penalty,
            net_salary    = net,
        ))

    await db.commit()

    return {
        "teacher_id":    str(teacher_id),
        "period":        f"{month}/{year}",
        "base_salary":   float(base),
        "total_bonus":   float(total_bonus),
        "total_penalty": float(total_penalty),
        "net_salary":    float(net),
        "results":       results,
    }


async def _compute_metric(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    metric: KpiMetric,
    month: int,
    year: int,
) -> Optional[Decimal]:
    """Metrika turiga qarab actual_value hisoblash."""

    if metric.slug == "attendance_punctuality":
        # Davomat o'z vaqtidaligi: teacher_id va oy bo'yicha attendance yozuvlari
        # "O'z vaqtida" = created_at - date farkı <= 24 soat (oddiy yondashuv)
        total = (await db.execute(
            select(func.count(Attendance.id)).where(
                and_(
                    Attendance.teacher_id   == teacher_id,
                    extract("month", Attendance.date) == month,
                    extract("year",  Attendance.date) == year,
                )
            )
        )).scalar_one()
        if total == 0:
            return Decimal("0")
        # O'z vaqtida kiritilgan = created_at - date <= 1 kun
        on_time = (await db.execute(
            select(func.count(Attendance.id)).where(
                and_(
                    Attendance.teacher_id   == teacher_id,
                    extract("month", Attendance.date) == month,
                    extract("year",  Attendance.date) == year,
                    func.date(Attendance.created_at) <= Attendance.date + timedelta(days=1),
                )
            )
        )).scalar_one()
        return Decimal(str(round(on_time / total * 100, 2)))

    if metric.slug == "student_attendance_rate":
        # O'qituvchi guruhlaridagi o'quvchi davomati o'rtachasi
        groups = (await db.execute(
            select(Group.id).where(
                and_(Group.teacher_id == teacher_id, Group.status == "active")
            )
        )).scalars().all()
        if not groups:
            return Decimal("0")
        total = (await db.execute(
            select(func.count(Attendance.id)).where(
                and_(
                    Attendance.group_id.in_(groups),
                    extract("month", Attendance.date) == month,
                    extract("year",  Attendance.date) == year,
                )
            )
        )).scalar_one()
        if total == 0:
            return Decimal("0")
        present = (await db.execute(
            select(func.count(Attendance.id)).where(
                and_(
                    Attendance.group_id.in_(groups),
                    extract("month", Attendance.date) == month,
                    extract("year",  Attendance.date) == year,
                    Attendance.status.in_(["present", "late"]),
                )
            )
        )).scalar_one()
        return Decimal(str(round(present / total * 100, 2)))

    # Boshqa metrikalar uchun null (qo'lda kiritiladi)
    return None


async def _find_matching_rule(
    db: AsyncSession,
    metric_id: uuid.UUID,
    actual: Optional[Decimal],
) -> Optional[KpiRule]:
    if actual is None:
        return None
    rules = (await db.execute(
        select(KpiRule).where(KpiRule.metric_id == metric_id)
        .order_by(KpiRule.threshold_min.desc())
    )).scalars().all()
    for rule in rules:
        lo = rule.threshold_min
        hi = rule.threshold_max
        if lo is not None and hi is not None:
            if lo <= actual <= hi:
                return rule
        elif lo is not None and actual >= lo:
            return rule
        elif hi is not None and actual <= hi:
            return rule
    return None


def _compute_reward(
    rule: KpiRule,
    base_salary: Optional[float],
    actual: Decimal,
) -> Decimal:
    base = Decimal(str(base_salary or 0))
    val  = Decimal(str(rule.reward_value))
    sign = -1 if rule.reward_type in ("penalty_pct", "penalty_sum") else 1

    if rule.reward_type in ("bonus_pct", "penalty_pct"):
        return Decimal(str(sign)) * (base * val / Decimal("100"))
    elif rule.reward_type in ("bonus_sum", "penalty_sum"):
        return Decimal(str(sign)) * val
    return Decimal("0")


# ─── Natijalar va slip ko'rish ────────────────────────────────────────

async def get_results(
    db: AsyncSession,
    teacher_id: Optional[uuid.UUID] = None,
    month: Optional[int]            = None,
    year:  Optional[int]            = None,
) -> List[dict]:
    stmt = select(KpiResult, KpiMetric).join(
        KpiMetric, KpiResult.metric_id == KpiMetric.id
    )
    if teacher_id: stmt = stmt.where(KpiResult.teacher_id == teacher_id)
    if month:      stmt = stmt.where(KpiResult.period_month == month)
    if year:       stmt = stmt.where(KpiResult.period_year  == year)
    rows = (await db.execute(stmt)).all()
    return [{
        "id":            str(r.id),
        "teacher_id":    str(r.teacher_id),
        "metric_slug":   m.slug,
        "metric_name":   m.name,
        "metric_unit":   m.unit,
        "period_month":  r.period_month,
        "period_year":   r.period_year,
        "actual_value":  float(r.actual_value) if r.actual_value is not None else None,
        "reward_amount": float(r.reward_amount),
        "status":        r.status,
        "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
    } for r, m in rows]


async def get_payslips(
    db: AsyncSession,
    teacher_id: Optional[uuid.UUID] = None,
    month: Optional[int]            = None,
    year:  Optional[int]            = None,
) -> List[dict]:
    stmt = select(KpiPayslip)
    if teacher_id: stmt = stmt.where(KpiPayslip.teacher_id   == teacher_id)
    if month:      stmt = stmt.where(KpiPayslip.period_month == month)
    if year:       stmt = stmt.where(KpiPayslip.period_year  == year)
    stmt = stmt.order_by(KpiPayslip.period_year.desc(), KpiPayslip.period_month.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_slip_dict(p) for p in rows]


async def approve_payslip(
    db: AsyncSession,
    payslip_id: uuid.UUID,
    approved_by: uuid.UUID,
) -> dict:
    slip = (await db.execute(
        select(KpiPayslip).where(KpiPayslip.id == payslip_id)
    )).scalar_one_or_none()
    if not slip:
        raise ValueError("Slip topilmadi")
    slip.status      = "approved"
    slip.approved_by = approved_by
    slip.approved_at = datetime.utcnow()

    # Barcha result larni approved ga o'tkazish
    results = (await db.execute(
        select(KpiResult).where(
            KpiResult.teacher_id   == slip.teacher_id,
            KpiResult.period_month == slip.period_month,
            KpiResult.period_year  == slip.period_year,
        )
    )).scalars().all()
    for r in results:
        r.status = "approved"

    await db.commit()
    await db.refresh(slip)
    return _slip_dict(slip)


# ─── Helpers ─────────────────────────────────────────────────────────

def _metric_dict(m: KpiMetric) -> dict:
    return {
        "id":          str(m.id),
        "slug":        m.slug,
        "name":        m.name,
        "description": m.description,
        "metric_type": m.metric_type,
        "direction":   m.direction,
        "unit":        m.unit,
        "is_active":   m.is_active,
    }


def _rule_dict(r: KpiRule) -> dict:
    return {
        "id":            str(r.id),
        "metric_id":     str(r.metric_id),
        "threshold_min": float(r.threshold_min) if r.threshold_min is not None else None,
        "threshold_max": float(r.threshold_max) if r.threshold_max is not None else None,
        "reward_type":   r.reward_type,
        "reward_value":  float(r.reward_value),
        "period":        r.period,
        "label":         r.label,
    }


def _slip_dict(p: KpiPayslip) -> dict:
    return {
        "id":            str(p.id),
        "teacher_id":    str(p.teacher_id),
        "period_month":  p.period_month,
        "period_year":   p.period_year,
        "base_salary":   float(p.base_salary),
        "total_bonus":   float(p.total_bonus),
        "total_penalty": float(p.total_penalty),
        "net_salary":    float(p.net_salary),
        "status":        p.status,
        "approved_at":   p.approved_at.isoformat() if p.approved_at else None,
        "pdf_url":       p.pdf_url,
    }
