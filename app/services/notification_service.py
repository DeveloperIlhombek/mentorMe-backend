"""
app/services/notification_service.py

Markaziy notification servis — barcha event source lar shu yerga keladi.

Mas'uliyatlari:
  1. Notification row durable yozadi (status=queued).
  2. NotificationPreference: per-category opt-out + quiet hours.
     Critical priority preferences ni override qiladi.
  3. Dedupe: oxirgi 24h da bir xil dedupe_key bo'lsa skip.
  4. Telegram channel → Celery task .delay()
  5. In-app channel → Redis pub/sub publish

Foydalanish:
    from app.services.notification_service import NotificationService

    svc = NotificationService(db, tenant_slug)
    await svc.enqueue(
        user_id=user.id, category="attendance", type="absence_alert",
        title="Bola darsda yo'q", body="...", data={"student_id": "..."},
        priority="high", dedupe_key=f"absent:{date}:{student_id}",
    )
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.tenant.notification import Notification
from app.models.tenant.notification_preference import NotificationPreference
from app.models.tenant.user import User

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "lesson", "attendance", "grade", "payment",
    "broadcast", "system", "kpi", "progress", "subscription",
}
VALID_PRIORITIES = {"low", "normal", "high", "critical"}
VALID_CHANNELS   = {"telegram", "in_app"}
# Critical kategoriyalar — preference o'chirishga ruxsat berilmaydi
CRITICAL_CATEGORIES = {"attendance", "payment", "system"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _in_quiet_hours(now: datetime, start: Optional[time], end: Optional[time]) -> bool:
    """
    Soat now (local) quiet hours [start, end) ichidami?
    end < start bo'lsa (22:00–07:00) — kun chegarasidan o'tadi.
    """
    if start is None or end is None:
        return False
    cur = now.time()
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end


def _next_quiet_end(now: datetime, end: time) -> datetime:
    """Quiet hours tugashi (UTC qaytariladi, sodda Tashkent assumption)."""
    candidate = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


class NotificationService:
    """Tenant scope ichida ishlaydi (db sessiya allaqachon search_path ga sozlangan)."""

    def __init__(self, db: AsyncSession, tenant_slug: str):
        self.db = db
        self.tenant_slug = tenant_slug

    async def enqueue(
        self,
        *,
        user_id: uuid.UUID,
        category: str,
        type: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        priority: str = "normal",
        dedupe_key: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        channels: Optional[list[str]] = None,
    ) -> Optional[Notification]:
        """
        Notification yaratadi va yuboradi. Skip bo'lsa None qaytaradi.
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Noto'g'ri category: {category}")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Noto'g'ri priority: {priority}")
        channels = channels or ["telegram", "in_app"]
        for ch in channels:
            if ch not in VALID_CHANNELS:
                raise ValueError(f"Noto'g'ri channel: {ch}")

        # ── Foydalanuvchi va preferences ──────────────────────────────
        user = (await self.db.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if not user or not user.is_active:
            logger.info(
                "notif.skip.user_missing tenant=%s user_id=%s",
                self.tenant_slug, user_id,
            )
            return None

        prefs = (await self.db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )).scalar_one_or_none()

        # ── Dedupe ────────────────────────────────────────────────────
        if dedupe_key:
            existing = (await self.db.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.dedupe_key == dedupe_key,
                    Notification.created_at >= _now_utc() - timedelta(hours=24),
                )
            )).scalar_one_or_none()
            if existing:
                logger.info(
                    "notif.skip.dedupe tenant=%s user_id=%s key=%s",
                    self.tenant_slug, user_id, dedupe_key,
                )
                return existing

        is_critical = priority == "critical" or category in CRITICAL_CATEGORIES

        # ── Preferences filtri ────────────────────────────────────────
        skip_telegram = False
        skip_in_app   = False
        delayed_until: Optional[datetime] = scheduled_at

        if prefs and not is_critical:
            if category in (prefs.disabled_categories or []):
                logger.info(
                    "notif.skip.category_disabled tenant=%s user_id=%s cat=%s",
                    self.tenant_slug, user_id, category,
                )
                return await self._record_skipped(
                    user_id, category, type, title, body, data,
                    priority, dedupe_key, "category_disabled",
                )
            if not prefs.telegram_enabled:
                skip_telegram = True
            if not prefs.in_app_enabled:
                skip_in_app = True

            # Quiet hours — kechiktirish
            if not delayed_until:
                now_local = _now_utc()  # tz-aware, tashkent +5
                if _in_quiet_hours(now_local, prefs.quiet_hours_start, prefs.quiet_hours_end):
                    delayed_until = _next_quiet_end(now_local, prefs.quiet_hours_end)

        if skip_telegram and "telegram" in channels:
            channels = [c for c in channels if c != "telegram"]
        if skip_in_app and "in_app" in channels:
            channels = [c for c in channels if c != "in_app"]

        if not channels:
            return await self._record_skipped(
                user_id, category, type, title, body, data,
                priority, dedupe_key, "all_channels_disabled",
            )

        # ── Notification row ──────────────────────────────────────────
        notif = Notification(
            user_id=user_id,
            type=type,
            category=category,
            priority=priority,
            title=title,
            body=body,
            data=data or {},
            channel="telegram" if "telegram" in channels else "in_app",
            status="queued",
            dedupe_key=dedupe_key,
            scheduled_at=delayed_until,
        )
        self.db.add(notif)
        await self.db.flush()
        notif_id = notif.id

        # ── Dispatch ──────────────────────────────────────────────────
        if "telegram" in channels and user.telegram_id:
            self._dispatch_telegram(notif_id, delayed_until)

        if "in_app" in channels:
            self._publish_in_app(user, notif)

        logger.info(
            "notif.enqueued tenant=%s user_id=%s cat=%s type=%s priority=%s scheduled=%s",
            self.tenant_slug, user_id, category, type, priority,
            delayed_until.isoformat() if delayed_until else None,
        )
        return notif

    async def enqueue_bulk(
        self,
        *,
        user_ids: list[uuid.UUID],
        category: str,
        type: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        priority: str = "normal",
        dedupe_key_prefix: Optional[str] = None,
        channels: Optional[list[str]] = None,
    ) -> list[Notification]:
        result: list[Notification] = []
        for uid in user_ids:
            dk = f"{dedupe_key_prefix}:{uid}" if dedupe_key_prefix else None
            n = await self.enqueue(
                user_id=uid, category=category, type=type,
                title=title, body=body, data=data,
                priority=priority, dedupe_key=dk, channels=channels,
            )
            if n:
                result.append(n)
        return result

    # ── Internal helpers ──────────────────────────────────────────────

    async def _record_skipped(
        self, user_id, category, type, title, body, data,
        priority, dedupe_key, reason,
    ) -> Notification:
        notif = Notification(
            user_id=user_id, type=type, category=category, priority=priority,
            title=title, body=body, data=data or {},
            channel="in_app", status="skipped", error=reason,
            dedupe_key=dedupe_key,
        )
        self.db.add(notif)
        await self.db.flush()
        return notif

    def _dispatch_telegram(
        self, notification_id: uuid.UUID, scheduled_at: Optional[datetime],
    ) -> None:
        """Celery task chaqirish (kechiktirish bo'lsa eta bilan)."""
        from app.tasks.notifications import send_telegram_notification
        kwargs = {"args": [str(notification_id), self.tenant_slug]}
        if scheduled_at:
            kwargs["eta"] = scheduled_at
        send_telegram_notification.apply_async(**kwargs)

    def _publish_in_app(self, user: User, notif: Notification) -> None:
        """Redis pub/sub orqali WebSocket consumer larga uzatish."""
        try:
            import redis
            r = redis.Redis.from_url(settings.REDIS_URL)
            payload = {
                "id":         str(notif.id),
                "type":       notif.type,
                "category":   notif.category,
                "priority":   notif.priority,
                "title":      notif.title,
                "body":       notif.body,
                "data":       notif.data,
                "created_at": _now_utc().isoformat(),
            }
            channel = f"notif:{self.tenant_slug}:{user.id}"
            r.publish(channel, json.dumps(payload))
        except Exception as e:
            logger.warning("notif.publish.failed err=%s", e)
