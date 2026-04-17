"""
app/api/v1/parent.py

Ota-ona paneli endpointlari:
  GET  /parent/children                      — farzandlar ro'yxati
  GET  /parent/children/{student_id}/profile — farzand profili
  GET  /parent/children/{student_id}/attendance
  GET  /parent/children/{student_id}/payments
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_parent
from app.models.tenant import Student, User
from app.schemas import ok
from app.services import attendance as att_svc
from app.services import payment as payment_svc

router = APIRouter(prefix="/parent", tags=["parent"])


async def _get_children(db: AsyncSession, parent_user_id: uuid.UUID):
    """Ota-onaning farzandlari."""
    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.parent_id == parent_user_id)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id":         str(s.id),
            "user_id":    str(s.user_id),
            "first_name": u.first_name,
            "last_name":  u.last_name,
            "balance":    float(s.balance),
            "is_active":  s.is_active,
        }
        for s, u in rows
    ]


@router.get("/children")
async def get_children(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_parent),
):
    """Farzandlar ro'yxati."""
    parent_id = uuid.UUID(tkn["sub"])
    children  = await _get_children(db, parent_id)
    return ok(children)


@router.get("/children/{student_id}/attendance")
async def get_child_attendance(
    student_id: uuid.UUID,
    month: Optional[int] = Query(None, ge=1, le=12),
    year:  Optional[int] = Query(None),
    db:    AsyncSession  = Depends(get_tenant_session),
    tkn:   dict          = Depends(require_parent),
):
    """Farzandning davomati."""
    result = await att_svc.get_student_history(db, student_id, month, year)
    return ok(result)


@router.get("/children/{student_id}/payments")
async def get_child_payments(
    student_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_parent),
):
    """Farzandning to'lov tarixi."""
    payments, total = await payment_svc.get_payments(db, student_id=student_id)
    return ok(payments, {"total": total})
