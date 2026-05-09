"""
app/api/v1/broadcast.py

Admin paneldan e'lon (broadcast) yuborish:
  POST   /api/v1/admin/broadcast        — yangi broadcast (rol/branch/group filtri)
  GET    /api/v1/admin/broadcast        — ro'yxat
  GET    /api/v1/admin/broadcast/{id}   — progress (sent/failed/total)
  POST   /api/v1/admin/broadcast/{id}/cancel  — bekor qilish

Body misol:
{
  "title":   "Bayram bilan!",
  "body":    "Aziz o'quvchilar, bayram bilan tabriklaymiz.",
  "filters": {"role": ["student", "parent"], "branch_id": null, "group_id": null},
  "channels": ["telegram", "in_app"]
}
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_tenant_session, get_tenant_slug, require_admin,
)
from app.models.tenant import BroadcastJob
from app.schemas import ok

router = APIRouter(prefix="/admin/broadcast", tags=["admin", "broadcast"])


VALID_ROLES = {"super_admin", "admin", "inspector", "teacher", "student", "parent"}


class BroadcastFilters(BaseModel):
    role:      Optional[list[str]]   = None
    branch_id: Optional[uuid.UUID]   = None
    group_id:  Optional[uuid.UUID]   = None


class BroadcastCreate(BaseModel):
    title:    str   = Field(..., min_length=1, max_length=200)
    body:     str   = Field(..., min_length=1, max_length=4000)
    filters:  BroadcastFilters = BroadcastFilters()
    channels: list[str] = Field(default_factory=lambda: ["telegram", "in_app"])
    data:     Optional[dict] = None


@router.post("", status_code=201)
async def create_broadcast(
    data:        BroadcastCreate,
    db:          AsyncSession = Depends(get_tenant_session),
    tenant_slug: str          = Depends(get_tenant_slug),
    tkn:         dict         = Depends(require_admin),
):
    """Broadcast yaratish va Celery ga yuborish."""
    # Validatsiya
    for role in (data.filters.role or []):
        if role not in VALID_ROLES:
            raise HTTPException(400, f"Noto'g'ri rol: {role}")
    for ch in data.channels:
        if ch not in {"telegram", "in_app"}:
            raise HTTPException(400, f"Noto'g'ri kanal: {ch}")

    job = BroadcastJob(
        created_by=uuid.UUID(tkn["sub"]),
        title=data.title,
        body=data.body,
        data=data.data or {},
        filters={
            "role":      data.filters.role,
            "branch_id": str(data.filters.branch_id) if data.filters.branch_id else None,
            "group_id":  str(data.filters.group_id) if data.filters.group_id else None,
        },
        channels=data.channels,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Celery task chaqirish
    from app.tasks.broadcast import run_broadcast
    run_broadcast.delay(str(job.id), tenant_slug)

    return ok(_job_dict(job))


@router.get("")
async def list_broadcasts(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
    limit: int = 50,
):
    rows = (await db.execute(
        select(BroadcastJob).order_by(BroadcastJob.created_at.desc()).limit(limit)
    )).scalars().all()
    return ok([_job_dict(j) for j in rows])


@router.get("/{job_id}")
async def get_broadcast(
    job_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    job = (await db.execute(
        select(BroadcastJob).where(BroadcastJob.id == job_id)
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Broadcast topilmadi")
    return ok(_job_dict(job))


@router.post("/{job_id}/cancel")
async def cancel_broadcast(
    job_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_admin),
):
    job = (await db.execute(
        select(BroadcastJob).where(BroadcastJob.id == job_id)
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Broadcast topilmadi")
    if job.status not in ("queued", "running"):
        raise HTTPException(400, "Bu holatda bekor qilib bo'lmaydi")
    job.status = "cancelled"
    await db.commit()
    return ok(_job_dict(job))


def _job_dict(j: BroadcastJob) -> dict:
    return {
        "id":         str(j.id),
        "title":      j.title,
        "body":       j.body,
        "filters":    j.filters,
        "channels":   j.channels,
        "total":      j.total,
        "sent":       j.sent,
        "failed":     j.failed,
        "status":     j.status,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }
