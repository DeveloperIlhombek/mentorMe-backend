"""app/api/v1/admin/branches.py — Filial endpointlari."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_tenant_session, get_optional_branch_filter,
    require_admin, require_inspector,
)
from app.schemas import ok
from app.services import branch as branch_svc

router = APIRouter(prefix="/branches", tags=["branches"])


# ─── Schemas ─────────────────────────────────────────────────────────

class BranchCreate(BaseModel):
    name:                      str
    address:                   Optional[str]       = None
    phone:                     Optional[str]       = None
    manager_id:                Optional[uuid.UUID] = None
    is_main:                   bool = False
    attendance_deadline_hours: int  = 2  # Davomat kiritish chegarasi (soat)


class BranchUpdate(BaseModel):
    name:                      Optional[str]  = None
    address:                   Optional[str]  = None
    phone:                     Optional[str]  = None
    is_main:                   Optional[bool] = None
    attendance_deadline_hours: Optional[int]  = None


class AssignInspector(BaseModel):
    user_id: uuid.UUID


class ExpenseCreate(BaseModel):
    title:       str
    amount:      float = Field(gt=0)
    category:    Optional[str] = None
    description: Optional[str] = None


class ExpenseReview(BaseModel):
    approve: bool
    reason:  Optional[str] = None


class TeacherRequestCreate(BaseModel):
    first_name:    str
    last_name:     Optional[str]  = None
    phone:         Optional[str]  = None
    subjects:      Optional[str]  = None   # "Ingliz tili, Matematika"
    salary_type:   Optional[str]  = None
    salary_amount: Optional[float]= None
    notes:         Optional[str]  = None


class RequestReview(BaseModel):
    approve: bool
    reason:  Optional[str] = None


# ─── Filiallar (faqat admin) ──────────────────────────────────────────

@router.get("")
async def list_branches(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),
):
    """Admin — barchasi, Inspector — faqat o'z filiali."""
    return ok(await branch_svc.get_branches(db))


@router.post("", status_code=201)
async def create_branch(
    data: BranchCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    result = await branch_svc.create_branch(
        db,
        name                      = data.name,
        address                   = data.address,
        phone                     = data.phone,
        manager_id                = data.manager_id,
        is_main                   = data.is_main,
        attendance_deadline_hours = data.attendance_deadline_hours,
    )
    return ok(result)


@router.get("/{branch_id}")
async def get_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_inspector),
):
    result = await branch_svc.get_branch(db, branch_id)
    if not result:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "Filial topilmadi")
    return ok(result)


@router.patch("/{branch_id}")
async def update_branch(
    branch_id: uuid.UUID,
    data: BranchUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    result = await branch_svc.update_branch(db, branch_id, **data.model_dump(exclude_none=True))
    return ok(result)


@router.delete("/{branch_id}", status_code=200)
async def delete_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    await branch_svc.delete_branch(db, branch_id)
    return ok({"message": "Filial arxivlandi"})


@router.get("/{branch_id}/stats")
async def branch_stats(
    branch_id: uuid.UUID,
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db: AsyncSession     = Depends(get_tenant_session),
    _:  dict             = Depends(require_inspector),
):
    return ok(await branch_svc.get_branch_stats(db, branch_id, month, year))


@router.get("/{branch_id}/dashboard")
async def branch_dashboard(
    branch_id: uuid.UUID,
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
    db: AsyncSession     = Depends(get_tenant_session),
    _:  dict             = Depends(require_inspector),
):
    """Filial uchun to'liq dashboard ma'lumotlari."""
    return ok(await branch_svc.get_branch_dashboard(db, branch_id, month, year))


# ─── Inspektor tayinlash ──────────────────────────────────────────────

@router.post("/{branch_id}/inspector")
async def assign_inspector(
    branch_id: uuid.UUID,
    data: AssignInspector,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    """Foydalanuvchini inspektor sifatida filiaga tayinlash."""
    result = await branch_svc.assign_inspector(db, branch_id, data.user_id)
    return ok(result)


@router.delete("/{branch_id}/inspector", status_code=200)
async def remove_inspector(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    await branch_svc.remove_inspector(db, branch_id)
    return ok({"message": "Inspektor olib tashlandi"})


# ─── Xarajatlar ───────────────────────────────────────────────────────

@router.get("/expenses/all")
async def list_all_expenses(
    status:    Optional[str]       = Query(None),
    branch_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession               = Depends(get_tenant_session),
    tkn: dict                      = Depends(require_inspector),
):
    """
    Admin — barcha filiallar xarajatlarini ko'radi.
    Inspektor — faqat o'z filiali xarajatlarini ko'radi.
    """
    role = tkn.get("role")
    filter_branch = branch_id

    if role == "inspector":
        # Inspektor faqat o'z filiali
        import uuid as _uuid
        from sqlalchemy import select
        from app.models.tenant.user import User
        user = (await db.execute(
            select(User).where(User.id == _uuid.UUID(tkn["sub"]))
        )).scalar_one_or_none()
        filter_branch = user.branch_id if user else None

    return ok(await branch_svc.get_expenses(db, filter_branch, status))


@router.post("/{branch_id}/expenses")
async def create_expense(
    branch_id: uuid.UUID,
    data: ExpenseCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_inspector),
):
    """Inspektor xarajat so'rovini yuboradi."""
    result = await branch_svc.create_expense_request(
        db,
        branch_id    = branch_id,
        requested_by = uuid.UUID(tkn["sub"]),
        title        = data.title,
        amount       = data.amount,
        category     = data.category,
        description  = data.description,
    )
    return ok(result)


@router.post("/expenses/{expense_id}/review")
async def review_expense(
    expense_id: uuid.UUID,
    data: ExpenseReview,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    """Admin xarajatni tasdiqlaydi yoki rad etadi."""
    result = await branch_svc.review_expense(
        db,
        expense_id = expense_id,
        admin_id   = uuid.UUID(tkn["sub"]),
        approve    = data.approve,
        reason     = data.reason,
    )
    return ok(result)


# ─── Inspektor so'rovlari (o'qituvchi qo'shish) ───────────────────────

@router.get("/requests/all")
async def list_requests(
    status:    Optional[str]       = Query(None),
    branch_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession               = Depends(get_tenant_session),
    tkn: dict                      = Depends(require_inspector),
):
    role = tkn.get("role")
    filter_branch = branch_id

    if role == "inspector":
        import uuid as _uuid
        from sqlalchemy import select
        from app.models.tenant.user import User
        user = (await db.execute(
            select(User).where(User.id == _uuid.UUID(tkn["sub"]))
        )).scalar_one_or_none()
        filter_branch = user.branch_id if user else None

    return ok(await branch_svc.get_inspector_requests(db, filter_branch, status))


@router.post("/{branch_id}/requests/teacher")
async def request_add_teacher(
    branch_id: uuid.UUID,
    data: TeacherRequestCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_inspector),
):
    """Inspektor yangi o'qituvchi qo'shish so'rovini yuboradi."""
    result = await branch_svc.create_teacher_request(
        db,
        branch_id    = branch_id,
        inspector_id = uuid.UUID(tkn["sub"]),
        first_name   = data.first_name,
        last_name    = data.last_name,
        phone        = data.phone,
        subjects     = data.subjects,
        salary_type  = data.salary_type,
        salary_amount= data.salary_amount,
        notes        = data.notes,
    )
    return ok(result)


@router.post("/requests/{request_id}/review")
async def review_request(
    request_id: uuid.UUID,
    data: RequestReview,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    """Admin so'rovni tasdiqlaydi yoki rad etadi."""
    result = await branch_svc.review_teacher_request(
        db,
        request_id = request_id,
        admin_id   = uuid.UUID(tkn["sub"]),
        approve    = data.approve,
        reason     = data.reason,
    )
    return ok(result)
