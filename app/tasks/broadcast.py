"""
app/tasks/broadcast.py

Broadcast Celery task — BroadcastJob filtrlariga mos foydalanuvchilarni tanlaydi
va har biriga notification yaratadi (send_telegram_notification.delay chaqiradi).
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


_sync_engine = None
_SyncSession = None


def _ensure_engine():
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        url = settings.DATABASE_URL.replace("+asyncpg", "")
        _sync_engine = create_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        _SyncSession = sessionmaker(bind=_sync_engine, autoflush=False, autocommit=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(name="app.tasks.broadcast.run_broadcast")
def run_broadcast(job_id: str, tenant_slug: str):
    """
    BroadcastJob ni bajarish:
      1. Filtrlar bo'yicha foydalanuvchilarni tanlash
      2. Har biriga Notification yozish + Celery .delay() qilish
      3. Job progress yangilash
    """
    schema = f"tenant_{tenant_slug.replace('-', '_')}"
    _ensure_engine()
    s = _SyncSession()
    try:
        s.execute(text(f'SET search_path TO "{schema}", public'))

        job_row = s.execute(text("""
            SELECT title, body, data, filters, channels, status
            FROM broadcast_jobs WHERE id = :id
        """), {"id": job_id}).first()
        if not job_row:
            logger.warning("broadcast.not_found id=%s", job_id)
            return
        title, body, data, filters, channels, status = job_row
        if status not in ("queued", "running"):
            logger.info("broadcast.skip status=%s id=%s", status, job_id)
            return

        s.execute(text("""
            UPDATE broadcast_jobs SET status='running', started_at=:ts WHERE id=:id
        """), {"ts": _now(), "id": job_id})
        s.commit()

        # ── Foydalanuvchilarni tanlash ─────────────────────────────
        roles     = (filters or {}).get("role")
        branch_id = (filters or {}).get("branch_id")
        group_id  = (filters or {}).get("group_id")

        sql = "SELECT id FROM users WHERE is_active=TRUE"
        params: dict = {}
        if roles:
            placeholders = ",".join(f":r{i}" for i in range(len(roles)))
            sql += f" AND role IN ({placeholders})"
            for i, r in enumerate(roles):
                params[f"r{i}"] = r
        if branch_id:
            sql += " AND branch_id = :bid"
            params["bid"] = branch_id
        if group_id:
            # Faqat shu guruhdagi studentlar (StudentGroup orqali)
            sql += """ AND id IN (
                SELECT s.user_id FROM students s
                JOIN student_groups sg ON sg.student_id = s.id
                WHERE sg.group_id = :gid AND sg.is_active=TRUE
            )"""
            params["gid"] = group_id

        user_rows = s.execute(text(sql), params).all()
        user_ids = [r[0] for r in user_rows]
        total    = len(user_ids)

        s.execute(text(
            "UPDATE broadcast_jobs SET total = :t WHERE id = :id"
        ), {"t": total, "id": job_id})
        s.commit()

        # ── Har user uchun Notification ────────────────────────────
        sent = 0
        failed = 0
        for uid in user_ids:
            # Job bekor qilinganmi?
            cur_status = s.execute(text(
                "SELECT status FROM broadcast_jobs WHERE id = :id"
            ), {"id": job_id}).scalar()
            if cur_status == "cancelled":
                logger.info("broadcast.cancelled id=%s", job_id)
                break

            try:
                nid = uuid.uuid4()
                s.execute(text("""
                    INSERT INTO notifications
                    (id, user_id, type, category, priority, title, body, data,
                     channel, status, dedupe_key)
                    VALUES (:id, :uid, 'broadcast', 'broadcast', 'normal',
                            :title, :body, CAST(:data AS JSONB),
                            :ch, 'queued', :dk)
                """), {
                    "id": str(nid), "uid": str(uid),
                    "title": title, "body": body,
                    "data": json.dumps(data or {}),
                    "ch": "telegram" if "telegram" in (channels or []) else "in_app",
                    "dk": f"broadcast:{job_id}:{uid}",
                })
                if "telegram" in (channels or []):
                    from app.tasks.notifications import send_telegram_notification
                    send_telegram_notification.delay(str(nid), tenant_slug)

                # In-app — Redis publish
                if "in_app" in (channels or []):
                    try:
                        import redis
                        r = redis.Redis.from_url(settings.REDIS_URL)
                        r.publish(
                            f"notif:{tenant_slug}:{uid}",
                            json.dumps({
                                "id": str(nid), "type": "broadcast",
                                "category": "broadcast", "priority": "normal",
                                "title": title, "body": body, "data": data or {},
                                "created_at": _now().isoformat(),
                            }),
                        )
                    except Exception as e:
                        logger.warning("broadcast.publish.failed err=%s", e)

                sent += 1
            except Exception as e:
                logger.warning("broadcast.user.failed uid=%s err=%s", uid, e)
                failed += 1

            if (sent + failed) % 100 == 0:
                s.execute(text("""
                    UPDATE broadcast_jobs SET sent=:s, failed=:f WHERE id=:id
                """), {"s": sent, "f": failed, "id": job_id})
                s.commit()

        s.execute(text("""
            UPDATE broadcast_jobs
            SET sent=:s, failed=:f, status='done', completed_at=:ts
            WHERE id=:id AND status != 'cancelled'
        """), {"s": sent, "f": failed, "ts": _now(), "id": job_id})
        s.commit()
        logger.info(
            "broadcast.done id=%s tenant=%s total=%s sent=%s failed=%s",
            job_id, tenant_slug, total, sent, failed,
        )

    except Exception as e:
        logger.exception("broadcast.error id=%s err=%s", job_id, e)
        try:
            s.execute(text("""
                UPDATE broadcast_jobs SET status='done', completed_at=:ts WHERE id=:id
            """), {"ts": _now(), "id": job_id})
            s.commit()
        except Exception:
            s.rollback()
    finally:
        s.close()
