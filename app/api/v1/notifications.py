"""
app/api/v1/notifications.py

Bildirishnomalar endpointlari:
  GET   /notifications        — o'qilmagan bildirishnomalar
  PATCH /notifications/{id}   — o'qilgan deb belgilash
  PATCH /notifications/read-all — barchasini o'qilgan deb belgilash
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_any
from app.models.tenant import Notification
from app.schemas import ok

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def get_notifications(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_any),
):
    """Joriy foydalanuvchining bildirishnomalari."""
    user_id = uuid.UUID(tkn["sub"])
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    rows = (await db.execute(stmt)).scalars().all()
    unread_count = sum(1 for r in rows if not r.is_read)

    return ok(
        [_notif_dict(n) for n in rows],
        {"unread_count": unread_count},
    )


@router.patch("/{notif_id}/read")
async def mark_read(
    notif_id: uuid.UUID,
    db:       AsyncSession = Depends(get_tenant_session),
    tkn:      dict         = Depends(require_any),
):
    """Bitta bildirishnomani o'qilgan deb belgilash."""
    user_id = uuid.UUID(tkn["sub"])
    stmt = (
        select(Notification)
        .where(
            Notification.id == notif_id,
            Notification.user_id == user_id,
        )
    )
    notif = (await db.execute(stmt)).scalar_one_or_none()
    if notif:
        notif.is_read = True
        from datetime import datetime
        notif.read_at = datetime.utcnow()
        await db.commit()

    return ok({"message": "O'qildi"})


@router.patch("/read-all")
async def mark_all_read(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_any),
):
    """Barcha bildirishnomalarni o'qilgan deb belgilash."""
    user_id = uuid.UUID(tkn["sub"])
    from datetime import datetime
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
        .values(is_read=True, read_at=datetime.utcnow())
    )
    await db.execute(stmt)
    await db.commit()
    return ok({"message": "Barchasi o'qildi"})


def _notif_dict(n: Notification) -> dict:
    return {
        "id":         str(n.id),
        "type":       n.type,
        "title":      n.title,
        "body":       n.body,
        "data":       n.data,
        "channel":    n.channel,
        "is_read":    n.is_read,
        "sent_at":    n.sent_at.isoformat() if n.sent_at else None,
        "created_at": n.created_at.isoformat(),
    }
