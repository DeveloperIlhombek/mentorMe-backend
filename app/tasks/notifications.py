"""
app/tasks/notifications.py

Celery task — Telegram orqali bildirishnoma yuborish.

Asosiy xususiyatlar:
  - Tenant schema search_path o'rnatiladi (sync sessiya ichida)
  - Retry: HTTP error, 429 (rate limit), 5xx
  - Do not retry: 403 (bot blocked), 400 (chat not found)
  - Rate limit: TELEGRAM_RATE_LIMIT_PER_SEC (~25/s)
  - Notification status: queued → sent | failed
"""
import logging
from datetime import datetime, timezone

import httpx
from celery.exceptions import Ignore
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ── Sync engine (Celery worker uchun) — lazy initialize ──────────────
_sync_engine = None
_SyncSession = None


def _get_session_factory():
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        url = settings.DATABASE_URL.replace("+asyncpg", "")  # psycopg (v3) default
        _sync_engine = create_engine(
            url, pool_size=5, max_overflow=10, pool_pre_ping=True,
        )
        _SyncSession = sessionmaker(bind=_sync_engine, autoflush=False, autocommit=False)
    return _SyncSession


def _tenant_session(tenant_slug: str) -> Session:
    schema = f"tenant_{tenant_slug.replace('-', '_')}"
    SessionFactory = _get_session_factory()
    s = SessionFactory()
    s.execute(text(f'SET search_path TO "{schema}", public'))
    return s


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────
# Asosiy yuboruvchi
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.tasks.notifications.send_telegram_notification",
    autoretry_for=(httpx.HTTPError, httpx.ConnectError, httpx.ReadTimeout),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
    rate_limit=f"{settings.TELEGRAM_RATE_LIMIT_PER_SEC}/s",
)
def send_telegram_notification(self, notification_id: str, tenant_slug: str):
    """
    Bitta notification ni Telegram orqali yuborish.
    notification_id — Notification.id (UUID string).
    """
    if not settings.BOT_TOKEN:
        logger.warning("send_telegram_notification: BOT_TOKEN sozlanmagan, skip")
        return

    session = _tenant_session(tenant_slug)
    try:
        row = session.execute(text("""
            SELECT n.id, n.user_id, n.title, n.body, n.data, n.attempts,
                   u.telegram_id, u.first_name
            FROM notifications n
            JOIN users u ON u.id = n.user_id
            WHERE n.id = :nid
        """), {"nid": notification_id}).first()

        if not row:
            logger.warning("notif.send.not_found id=%s", notification_id)
            return

        nid, user_id, title, body, data, attempts, telegram_id, first_name = row

        if not telegram_id:
            session.execute(text("""
                UPDATE notifications
                SET status='failed', error='not_linked', attempts=attempts+1
                WHERE id = :nid
            """), {"nid": nid})
            session.commit()
            logger.info("notif.send.skip.not_linked tenant=%s user_id=%s", tenant_slug, user_id)
            return

        # ── Message body tayyorlash ────────────────────────────────
        message_text = f"<b>{title}</b>\n\n{body}"

        payload = {
            "chat_id": int(telegram_id),
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        # Inline keyboard data dan
        if isinstance(data, dict) and data.get("buttons"):
            payload["reply_markup"] = {"inline_keyboard": data["buttons"]}

        # ── Telegram API ───────────────────────────────────────────
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                json=payload, timeout=15,
            )
        except httpx.HTTPError:
            session.execute(text("UPDATE notifications SET attempts=attempts+1 WHERE id=:nid"),
                            {"nid": nid})
            session.commit()
            raise

        if resp.status_code == 200:
            session.execute(text("""
                UPDATE notifications
                SET status='sent', sent_at=:ts, attempts=attempts+1
                WHERE id = :nid
            """), {"nid": nid, "ts": _now_utc()})
            session.commit()
            logger.info(
                "notif.send.ok tenant=%s user_id=%s notif=%s",
                tenant_slug, user_id, nid,
            )
            return

        # 429 → retry-after
        if resp.status_code == 429:
            retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
            session.execute(text("UPDATE notifications SET attempts=attempts+1 WHERE id=:nid"),
                            {"nid": nid})
            session.commit()
            logger.warning("notif.send.429 tenant=%s retry_after=%s", tenant_slug, retry_after)
            raise self.retry(countdown=retry_after, max_retries=5)

        # 403 — bot bloklangan, 400 — chat topilmadi → do not retry
        if resp.status_code in (400, 403):
            error_msg = resp.json().get("description", f"http_{resp.status_code}")
            session.execute(text("""
                UPDATE notifications
                SET status='failed', error=:err, attempts=attempts+1
                WHERE id = :nid
            """), {"nid": nid, "err": error_msg[:500]})
            session.commit()
            logger.warning(
                "notif.send.blocked tenant=%s user_id=%s status=%s err=%s",
                tenant_slug, user_id, resp.status_code, error_msg,
            )
            return

        # Boshqa 5xx — retry
        session.execute(text("UPDATE notifications SET attempts=attempts+1 WHERE id=:nid"),
                        {"nid": nid})
        session.commit()
        raise self.retry(countdown=10, max_retries=5)

    except Ignore:
        raise
    except Exception as e:
        logger.exception("notif.send.error tenant=%s err=%s", tenant_slug, e)
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────
# Quiet hours scheduled — vaqti kelgan kechiktirilganlarni yuborish
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.notifications.flush_scheduled")
def flush_scheduled():
    """
    Har 1 minutda: quiet hours tugagan scheduled notification larni dispatch.
    (Celery eta allaqachon ishlaydi, lekin worker o'lib qolgan bo'lsa zaxira.)
    """
    SessionFactory = _get_session_factory()
    eng = _sync_engine
    with eng.connect() as conn:
        tenants = conn.execute(text(
            "SELECT slug, schema_name FROM public.tenants WHERE is_active=TRUE"
        )).all()

    total = 0
    for slug, schema in tenants:
        s = SessionFactory()
        try:
            s.execute(text(f'SET search_path TO "{schema}", public'))
            rows = s.execute(text("""
                SELECT id FROM notifications
                WHERE status='queued'
                  AND scheduled_at IS NOT NULL
                  AND scheduled_at <= NOW()
                LIMIT 500
            """)).all()
            for (nid,) in rows:
                send_telegram_notification.delay(str(nid), slug)
                total += 1
        finally:
            s.close()

    if total:
        logger.info("notif.flush.scheduled count=%s", total)


# ─────────────────────────────────────────────────────────────────────
# Helper — Celery'dan tashqari (bot handlerlardan) chaqiriladigan
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.notifications.send_telegram_message")
def send_telegram_message(telegram_id: int, text_msg: str, parse_mode: str = "HTML"):
    """Sodda Telegram message — Notification jadvalsiz (legacy support)."""
    if not settings.BOT_TOKEN:
        return
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            json={"chat_id": telegram_id, "text": text_msg, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("telegram_message_sent telegram_id=%s", telegram_id)
    except Exception as e:
        logger.error("telegram_message_failed telegram_id=%s err=%s", telegram_id, e)
