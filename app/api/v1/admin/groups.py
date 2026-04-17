"""
app/api/v1/admin/groups.py

Guruhlar boshqaruvi endpointlari.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_optional_branch_filter,
    get_tenant_session,
    require_admin,
    require_inspector,
    require_teacher,
)
from app.schemas import GroupCreate, GroupUpdate, ok
from app.services import group as group_svc

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("")
async def list_groups(
    page:       int                  = Query(1, ge=1),
    per_page:   int                  = Query(20, ge=1, le=100),
    search:     Optional[str]        = Query(None),
    status:     Optional[str]        = Query(None),
    teacher_id: Optional[uuid.UUID]  = Query(None),
    db: AsyncSession                 = Depends(get_tenant_session),
    _:  dict                         = Depends(require_teacher),
    branch_filter: Optional[str]     = Depends(get_optional_branch_filter),
):
    """Guruhlar ro'yxati."""
    import uuid as _uuid
    branch_id_f = _uuid.UUID(branch_filter) if branch_filter else None
    groups, total = await group_svc.get_groups(
        db, page=page, per_page=per_page,
        search=search, status=status, teacher_id=teacher_id,
        branch_id=branch_id_f,
    )
    pages = (total + per_page - 1) // per_page
    return ok(groups, {
        "page": page, "per_page": per_page,
        "total": total, "total_pages": pages,
    })


@router.post("", status_code=201)
async def create_group(
    data: GroupCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_inspector),
):
    """Yangi guruh yaratish."""
    result = await group_svc.create(db, data)
    return ok(result)


@router.get("/{group_id}")
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """Bitta guruh to'liq ma'lumoti."""
    result = await group_svc.get_by_id(db, group_id)
    return ok(result)


@router.patch("/{group_id}")
async def update_group(
    group_id: uuid.UUID,
    data: GroupUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_inspector),
):
    """Guruh ma'lumotlarini yangilash."""
    result = await group_svc.update(db, group_id, data)
    return ok(result)


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    """Guruhni yopish (status → completed)."""
    await group_svc.delete(db, group_id)


@router.get("/{group_id}/students")
async def get_group_students(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """Guruh o'quvchilari ro'yxati."""
    students = await group_svc.get_students(db, group_id)
    return ok(students)