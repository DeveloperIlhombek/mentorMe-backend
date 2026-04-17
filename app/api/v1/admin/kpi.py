"""app/api/v1/admin/kpi.py — KPI endpointlari."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_teacher
from app.schemas import ok
from app.services import kpi as kpi_svc

router = APIRouter(prefix="/kpi", tags=["kpi"])


# ─── Schemas ─────────────────────────────────────────────────────────

class MetricCreate(BaseModel):
    slug:        str = Field(min_length=2, max_length=80)
    name:        str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    metric_type: str = "percentage"
    direction:   str = "higher_better"
    unit:        str = "%"

    @field_validator("metric_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in ("percentage", "count", "rating", "sum", "custom"):
            raise ValueError("Noto'g'ri metric_type")
        return v


class MetricUpdate(BaseModel):
    name:        Optional[str] = None
    description: Optional[str] = None
    unit:        Optional[str] = None
    is_active:   Optional[bool] = None


class RuleCreate(BaseModel):
    metric_id:     uuid.UUID
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    reward_type:   str
    reward_value:  float = Field(ge=0)
    label:         Optional[str] = None
    period:        str = "monthly"

    @field_validator("reward_type")
    @classmethod
    def check_reward(cls, v: str) -> str:
        valid = ("bonus_pct", "bonus_sum", "penalty_pct", "penalty_sum", "none")
        if v not in valid:
            raise ValueError(f"reward_type: {valid}")
        return v


# ─── Metrikalar ──────────────────────────────────────────────────────

@router.get("/metrics")
async def list_metrics(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """Barcha aktiv metrikalar (o'qituvchi + admin ko'radi)."""
    return ok(await kpi_svc.get_metrics(db))


@router.post("/metrics", status_code=201)
async def create_metric(
    data: MetricCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    result = await kpi_svc.create_metric(
        db,
        slug=data.slug, name=data.name,
        metric_type=data.metric_type, direction=data.direction,
        unit=data.unit, description=data.description,
        created_by=uuid.UUID(tkn["sub"]),
    )
    return ok(result)


@router.patch("/metrics/{metric_id}")
async def update_metric(
    metric_id: uuid.UUID,
    data: MetricUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    result = await kpi_svc.update_metric(db, metric_id, **data.model_dump(exclude_none=True))
    return ok(result)


@router.delete("/metrics/{metric_id}", status_code=200)
async def delete_metric(
    metric_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    await kpi_svc.delete_metric(db, metric_id)
    return ok({"message": "Metrika o'chirildi"})


# ─── Qoidalar ────────────────────────────────────────────────────────

@router.get("/rules")
async def list_rules(
    metric_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession               = Depends(get_tenant_session),
    _:  dict                       = Depends(require_admin),
):
    return ok(await kpi_svc.get_rules(db, metric_id))


@router.post("/rules", status_code=201)
async def create_rule(
    data: RuleCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    result = await kpi_svc.create_rule(
        db,
        metric_id     = data.metric_id,
        reward_type   = data.reward_type,
        reward_value  = Decimal(str(data.reward_value)),
        threshold_min = Decimal(str(data.threshold_min)) if data.threshold_min is not None else None,
        threshold_max = Decimal(str(data.threshold_max)) if data.threshold_max is not None else None,
        label         = data.label,
        period        = data.period,
    )
    return ok(result)


@router.delete("/rules/{rule_id}", status_code=200)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    await kpi_svc.delete_rule(db, rule_id)
    return ok({"message": "Qoida o'chirildi"})


# ─── Hisoblash ───────────────────────────────────────────────────────

@router.post("/calculate")
async def calculate_kpi(
    teacher_id: uuid.UUID,
    month: int = Query(..., ge=1, le=12),
    year:  int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Admin qo'lda KPI hisoblash (istalgan vaqt)."""
    result = await kpi_svc.calculate_for_teacher(db, teacher_id, month, year)
    return ok(result)


@router.post("/calculate/all")
async def calculate_all_kpi(
    month: int = Query(..., ge=1, le=12),
    year:  int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Barcha o'qituvchilar uchun KPI hisoblash (oy tanlash)."""
    from sqlalchemy import select
    from app.models.tenant.teacher import Teacher

    teachers = (await db.execute(
        select(Teacher).where(Teacher.is_active == True)
    )).scalars().all()

    results = []
    for t in teachers:
        try:
            r = await kpi_svc.calculate_for_teacher(db, t.id, month, year)
            results.append(r)
        except Exception as e:
            results.append({"teacher_id": str(t.id), "error": str(e)})

    return ok(results, {"total": len(results)})


# ─── Natijalar ───────────────────────────────────────────────────────

@router.get("/results")
async def get_results(
    teacher_id: Optional[uuid.UUID] = Query(None),
    month:      Optional[int]       = Query(None, ge=1, le=12),
    year:       Optional[int]       = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_teacher),
):
    return ok(await kpi_svc.get_results(db, teacher_id, month, year))


@router.get("/teacher/my-results")
async def my_kpi_results(
    month: Optional[int] = Query(None, ge=1, le=12),
    year:  Optional[int] = Query(None),
    db: AsyncSession     = Depends(get_tenant_session),
    tkn: dict            = Depends(require_teacher),
):
    """O'qituvchi o'z KPI natijalarini ko'radi."""
    from sqlalchemy import select
    from app.models.tenant.teacher import Teacher

    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == uuid.UUID(tkn["sub"]))
    )).scalar_one_or_none()

    if not teacher:
        return ok([], {"total": 0})

    results  = await kpi_svc.get_results(db, teacher.id, month, year)
    payslips = await kpi_svc.get_payslips(db, teacher.id, month, year)
    return ok({"results": results, "payslips": payslips})


# ─── Payslip ─────────────────────────────────────────────────────────

@router.get("/payslips")
async def list_payslips(
    teacher_id: Optional[uuid.UUID] = Query(None),
    month:      Optional[int]       = Query(None),
    year:       Optional[int]       = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_admin),
):
    return ok(await kpi_svc.get_payslips(db, teacher_id, month, year))


@router.post("/payslips/{payslip_id}/approve")
async def approve_payslip(
    payslip_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    result = await kpi_svc.approve_payslip(db, payslip_id, uuid.UUID(tkn["sub"]))
    return ok(result)


# ─── O'qituvchi KPI sanasi sozlash ───────────────────────────────────

class KpiCalcDayUpdate(BaseModel):
    kpi_calc_day: int = Field(ge=1, le=31)


@router.patch("/teacher/{teacher_id}/calc-day")
async def set_teacher_calc_day(
    teacher_id: uuid.UUID,
    data: KpiCalcDayUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    """O'qituvchining oylik KPI hisoblash kunini belgilash."""
    from sqlalchemy import select
    from app.models.tenant.teacher import Teacher

    teacher = (await db.execute(
        select(Teacher).where(Teacher.id == teacher_id)
    )).scalar_one_or_none()
    if not teacher:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "O'qituvchi topilmadi")

    teacher.kpi_calc_day = data.kpi_calc_day
    await db.commit()
    return ok({"teacher_id": str(teacher_id), "kpi_calc_day": data.kpi_calc_day})
