"""
app/api/v1/notifications.py

Notification endpointlari:
  GET    /notifications                  — joriy foydalanuvchi notification ro'yxati
  PATCH  /notifications/{id}/read        — bittasini o'qildi
  PATCH  /notifications/read-all         — barchasini o'qildi
  GET    /notifications/preferences      — foydalanuvchi preferences
  PATCH  /notifications/preferences      — preferences yangilash
"""
import uuid
from datetime import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_any
from app.models.tenant import Notification, NotificationPreference
from app.schemas import ok

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ─── Preferences ──────────────────────────────────────────────────────

class PreferenceUpdate(BaseModel):
    telegram_enabled:    Optional[bool]      = None
    in_app_enabled:      Optional[bool]      = None
    disabled_categories: Optional[list[str]] = None
    quiet_hours_start:   Optional[str]       = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end:     Optional[str]       = Field(None, pattern=r"^\d{2}:\d{2}$")


@router.get("/preferences")
async def get_preferences(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_any),
):
    user_id = uuid.UUID(tkn["sub"])
    pref = (await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )).scalar_one_or_none()

    if not pref:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        await db.commit()
        await db.refresh(pref)

    return ok(_pref_dict(pref))


@router.patch("/preferences")
async def update_preferences(
    data: PreferenceUpdate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_any),
):
    user_id = uuid.UUID(tkn["sub"])
    pref = (await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )).scalar_one_or_none()

    if not pref:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        await db.flush()

    if data.telegram_enabled is not None:
        pref.telegram_enabled = data.telegram_enabled
    if data.in_app_enabled is not None:
        pref.in_app_enabled = data.in_app_enabled
    if data.disabled_categories is not None:
        # Critical kategoriyalarni o'chirishga ruxsat berilmaydi
        from app.services.notification_service import CRITICAL_CATEGORIES
        pref.disabled_categories = [
            c for c in data.disabled_categories if c not in CRITICAL_CATEGORIES
        ]
    if data.quiet_hours_start is not None:
        pref.quiet_hours_start = _parse_time(data.quiet_hours_start)
    if data.quiet_hours_end is not None:
        pref.quiet_hours_end = _parse_time(data.quiet_hours_end)

    await db.commit()
    await db.refresh(pref)
    return ok(_pref_dict(pref))


# ─── List ─────────────────────────────────────────────────────────────

@router.get("")
async def get_notifications(
    db:        AsyncSession   = Depends(get_tenant_session),
    tkn:       dict           = Depends(require_any),
    category:  Optional[str]  = Query(None),
    is_read:   Optional[bool] = Query(None),
    limit:     int            = Query(50, ge=1, le=200),
    offset:    int            = Query(0, ge=0),
):
    user_id = uuid.UUID(tkn["sub"])
    stmt = select(Notification).where(Notification.user_id == user_id)
    if category:
        stmt = stmt.where(Notification.category == category)
    if is_read is not None:
        stmt = stmt.where(Notification.is_read == is_read)
    stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    unread_count = (await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
    )).scalars().all()
    return ok(
        [_notif_dict(n) for n in rows],
        {"unread_count": len(unread_count)},
    )


@router.patch("/{notif_id}/read")
async def mark_read(
    notif_id: uuid.UUID,
    db:       AsyncSession = Depends(get_tenant_session),
    tkn:      dict         = Depends(require_any),
):
    user_id = uuid.UUID(tkn["sub"])
    notif = (await db.execute(
        select(Notification).where(
            Notification.id == notif_id,
            Notification.user_id == user_id,
        )
    )).scalar_one_or_none()
    if notif:
        from datetime import datetime
        notif.is_read = True
        notif.read_at = datetime.utcnow()
        await db.commit()
    return ok({"message": "O'qildi"})


@router.patch("/read-all")
async def mark_all_read(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_any),
):
    user_id = uuid.UUID(tkn["sub"])
    from datetime import datetime
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
        .values(is_read=True, read_at=datetime.utcnow())
    )
    await db.commit()
    return ok({"message": "Barchasi o'qildi"})


# ─── Helpers ──────────────────────────────────────────────────────────

def _notif_dict(n: Notification) -> dict:
    return {
        "id":         str(n.id),
        "type":       n.type,
        "category":   n.category,
        "priority":   n.priority,
        "title":      n.title,
        "body":       n.body,
        "data":       n.data,
        "channel":    n.channel,
        "status":     n.status,
        "is_read":    n.is_read,
        "sent_at":    n.sent_at.isoformat() if n.sent_at else None,
        "created_at": n.created_at.isoformat(),
    }


def _pref_dict(p: NotificationPreference) -> dict:
    return {
        "telegram_enabled":    p.telegram_enabled,
        "in_app_enabled":      p.in_app_enabled,
        "disabled_categories": p.disabled_categories or [],
        "quiet_hours_start":   p.quiet_hours_start.strftime("%H:%M") if p.quiet_hours_start else None,
        "quiet_hours_end":     p.quiet_hours_end.strftime("%H:%M") if p.quiet_hours_end else None,
        "timezone":            p.timezone,
    }


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))
