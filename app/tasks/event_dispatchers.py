"""
app/tasks/event_dispatchers.py

Beat-driven dispatcher tasks — barcha tenantlar bo'ylab yuradi va
har bir tenant uchun mos eventlarga ko'ra notification yaratadi.

Har bir task:
  1. public.tenants jadvalidan aktiv tenant ro'yxatini oladi
  2. Har tenant schema ga search_path ni o'rnatadi
  3. Triggerlangan eventlarni topadi
  4. Notification ni queued holatda yozib, send_telegram_notification.delay(...) chaqiradi
"""
import logging
from datetime import datetime, timedelta, date, time as dtime
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

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


def _all_tenants() -> list[tuple[str, str]]:
    """[(slug, schema_name), ...]"""
    _ensure_engine()
    with _sync_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT slug, schema_name FROM public.tenants WHERE is_active=TRUE"
        )).all()
    return [(slug, schema) for slug, schema in rows]


def _tenant_session(schema: str) -> Session:
    _ensure_engine()
    s = _SyncSession()
    s.execute(text(f'SET search_path TO "{schema}", public'))
    return s


def _enqueue_sync(
    session: Session,
    tenant_slug: str,
    user_id,
    *,
    category: str,
    type: str,
    title: str,
    body: str,
    data: dict | None = None,
    priority: str = "normal",
    dedupe_key: str | None = None,
) -> str | None:
    """
    Sync mode: Notification row qo'shadi va Telegram task ni dispatch qiladi.
    Async NotificationService dan farqi — sync sessiya, no preferences quiet hours
    (Beat tasklar har 5 min/kun yuradi, quiet hours ni Celery sender hal qiladi).
    """
    # Dedupe
    if dedupe_key:
        existing = session.execute(text("""
            SELECT id FROM notifications
            WHERE user_id = :uid AND dedupe_key = :dk
              AND created_at >= NOW() - INTERVAL '24 hours'
        """), {"uid": str(user_id), "dk": dedupe_key}).first()
        if existing:
            return None

    import uuid, json
    nid = uuid.uuid4()
    session.execute(text("""
        INSERT INTO notifications
        (id, user_id, type, category, priority, title, body, data,
         channel, status, dedupe_key)
        VALUES (:id, :uid, :type, :cat, :pri, :title, :body, CAST(:data AS JSONB),
                'telegram', 'queued', :dk)
    """), {
        "id": str(nid), "uid": str(user_id), "type": type, "cat": category,
        "pri": priority, "title": title, "body": body,
        "data": json.dumps(data or {}), "dk": dedupe_key,
    })

    from app.tasks.notifications import send_telegram_notification
    send_telegram_notification.delay(str(nid), tenant_slug)
    return str(nid)


# ─────────────────────────────────────────────────────────────────────
# 1. Dars eslatmasi — har 5 min, 30 min qolgan darslar
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.event_dispatchers.dispatch_lesson_reminders")
def dispatch_lesson_reminders():
    """30 minutdan keyin boshlanadigan darslar — student + teacher ga eslatma."""
    now = datetime.now()
    target_dt = now + timedelta(minutes=30)
    dow = target_dt.isoweekday()  # 1=Du..7=Ya
    target_time = target_dt.strftime("%H:%M")
    today_iso   = now.date().isoformat()

    sent = 0
    for slug, schema in _all_tenants():
        s = _tenant_session(schema)
        try:
            groups = s.execute(text("""
                SELECT id, name, schedule, teacher_id FROM groups
                WHERE status='active' AND schedule IS NOT NULL
            """)).all()

            for gid, name, schedule, teacher_user_id in groups:
                if not schedule:
                    continue
                slot = next(
                    (sl for sl in schedule
                     if isinstance(sl, dict) and sl.get("day") == dow
                     and sl.get("start") == target_time),
                    None,
                )
                if not slot:
                    continue

                # Studentlar
                students = s.execute(text("""
                    SELECT s.user_id FROM student_groups sg
                    JOIN students s ON s.id = sg.student_id
                    WHERE sg.group_id = :gid AND sg.is_active = TRUE
                      AND s.is_active = TRUE AND s.user_id IS NOT NULL
                """), {"gid": str(gid)}).all()

                for (uid,) in students:
                    nid = _enqueue_sync(
                        s, slug, uid,
                        category="lesson", type="lesson_reminder",
                        priority="normal",
                        title=f"📚 {name} — 30 minutdan keyin",
                        body=f"<b>{name}</b> darsi soat <b>{target_time}</b> da boshlanadi.",
                        data={"group_id": str(gid), "starts_at": target_time},
                        dedupe_key=f"lesson:{today_iso}:{target_time}:{gid}:{uid}",
                    )
                    if nid:
                        sent += 1

                # O'qituvchi (Teacher.user_id orqali)
                if teacher_user_id:
                    t_user = s.execute(text("""
                        SELECT user_id FROM teachers WHERE id = :tid
                    """), {"tid": str(teacher_user_id)}).first()
                    if t_user and t_user[0]:
                        _enqueue_sync(
                            s, slug, t_user[0],
                            category="lesson", type="lesson_reminder_teacher",
                            priority="normal",
                            title=f"🎓 {name} — 30 minutdan keyin",
                            body=f"<b>{name}</b> darsi soat <b>{target_time}</b> da.",
                            data={"group_id": str(gid)},
                            dedupe_key=f"lesson_t:{today_iso}:{target_time}:{gid}",
                        )

            s.commit()
        except Exception as e:
            logger.exception("dispatch_lesson_reminders.tenant.error tenant=%s err=%s", slug, e)
            s.rollback()
        finally:
            s.close()

    logger.info("dispatch_lesson_reminders.done sent=%s", sent)


# ─────────────────────────────────────────────────────────────────────
# 2. Davomat eslatmasi — teacherlarga
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.event_dispatchers.dispatch_attendance_pending_reminder")
def dispatch_attendance_pending_reminder():
    """Bugun dars bo'lgan, lekin teacher davomat kiritmagan guruhlar."""
    today = date.today()
    dow = today.isoweekday()

    for slug, schema in _all_tenants():
        s = _tenant_session(schema)
        try:
            rows = s.execute(text("""
                SELECT g.id, g.name, g.schedule, t.user_id
                FROM groups g
                JOIN teachers t ON t.id = g.teacher_id
                WHERE g.status='active' AND g.schedule IS NOT NULL
                  AND t.user_id IS NOT NULL
            """)).all()

            for gid, name, schedule, teacher_user_id in rows:
                if not any(sl.get("day") == dow for sl in (schedule or []) if isinstance(sl, dict)):
                    continue

                marked = s.execute(text("""
                    SELECT 1 FROM attendance
                    WHERE group_id = :gid AND date = :d LIMIT 1
                """), {"gid": str(gid), "d": today}).first()
                if marked:
                    continue

                _enqueue_sync(
                    s, slug, teacher_user_id,
                    category="attendance", type="attendance_pending",
                    priority="high",
                    title=f"⏰ Davomat kiriting: {name}",
                    body=f"Siz bugungi <b>{name}</b> guruhi davomatini hali kiritmagansiz.",
                    data={"group_id": str(gid), "date": today.isoformat()},
                    dedupe_key=f"att_pending:{today.isoformat()}:{gid}",
                )

            s.commit()
        except Exception as e:
            logger.exception("dispatch_attendance_pending.tenant.error tenant=%s err=%s", slug, e)
            s.rollback()
        finally:
            s.close()


# ─────────────────────────────────────────────────────────────────────
# 3. Progress (baholash) deadline eslatmasi
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.event_dispatchers.dispatch_progress_deadline_reminder")
def dispatch_progress_deadline_reminder():
    """Baholash deadline yaqinlashgan guruhlar — teacherga eslatma."""
    today = date.today()

    for slug, schema in _all_tenants():
        s = _tenant_session(schema)
        try:
            rows = s.execute(text("""
                SELECT g.id, g.name, g.progress_deadline_day, t.user_id
                FROM groups g
                JOIN teachers t ON t.id = g.teacher_id
                WHERE g.status='active' AND g.progress_deadline_day IS NOT NULL
                  AND t.user_id IS NOT NULL
            """)).all()

            for gid, name, dline_day, teacher_user_id in rows:
                if dline_day is None:
                    continue
                days_left = dline_day - today.day
                if days_left not in (3, 1, 0):  # 3 kun, 1 kun, deadline kuni
                    continue

                pending_count = s.execute(text("""
                    SELECT COUNT(*) FROM students s
                    JOIN student_groups sg ON sg.student_id = s.id
                    WHERE sg.group_id = :gid AND sg.is_active = TRUE
                      AND s.is_active = TRUE
                      AND NOT EXISTS (
                        SELECT 1 FROM student_progress sp
                        WHERE sp.student_id = s.id
                          AND sp.group_id = :gid
                          AND sp.period_month = :m AND sp.period_year = :y
                          AND sp.status = 'entered'
                      )
                """), {
                    "gid": str(gid), "m": today.month, "y": today.year,
                }).scalar()

                if pending_count == 0:
                    continue

                _enqueue_sync(
                    s, slug, teacher_user_id,
                    category="progress", type="progress_deadline",
                    priority="high" if days_left <= 1 else "normal",
                    title=f"📈 Baholash deadline — {days_left} kun qoldi",
                    body=(
                        f"<b>{name}</b> guruhida {pending_count} ta o'quvchi uchun "
                        f"baho kiritilmagan. Deadline: {today.year}-{today.month:02d}-{dline_day:02d}."
                    ),
                    data={"group_id": str(gid), "pending": pending_count,
                          "month": today.month, "year": today.year},
                    dedupe_key=f"progress_dl:{today.year}-{today.month}-{dline_day}:{gid}:{days_left}",
                )

            s.commit()
        except Exception as e:
            logger.exception("dispatch_progress_deadline.tenant.error tenant=%s err=%s", slug, e)
            s.rollback()
        finally:
            s.close()


# ─────────────────────────────────────────────────────────────────────
# 4. To'lov eslatmasi — har oy 25 da
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.event_dispatchers.dispatch_payment_reminders")
def dispatch_payment_reminders():
    """Keyingi oyga to'lov vaqti yaqin — student + parent."""
    today = date.today()

    for slug, schema in _all_tenants():
        s = _tenant_session(schema)
        try:
            rows = s.execute(text("""
                SELECT s.id, s.user_id, s.parent_id, s.balance, s.monthly_fee,
                       u.first_name, u.last_name
                FROM students s
                JOIN users u ON u.id = s.user_id
                WHERE s.is_active=TRUE AND s.monthly_fee > 0
                  AND s.balance < s.monthly_fee
            """)).all()

            for sid, user_id, parent_id, balance, fee, fname, lname in rows:
                stud_name = f"{fname} {lname or ''}".strip()
                debt = float(fee) - float(balance or 0)
                amount_str = f"{debt:,.0f}".replace(",", " ")
                title = "💰 To'lov vaqti yaqin"
                body  = (
                    f"Keyingi oy uchun to'lov: <b>{amount_str} so'm</b>.\n"
                    f"Iltimos, oy oxirigacha to'lashingizni so'raymiz."
                )

                if user_id:
                    _enqueue_sync(
                        s, slug, user_id,
                        category="payment", type="payment_reminder",
                        priority="normal", title=title, body=body,
                        data={"amount": debt, "month": today.month, "year": today.year},
                        dedupe_key=f"pay_remind:{today.year}-{today.month}:student:{sid}",
                    )
                if parent_id:
                    _enqueue_sync(
                        s, slug, parent_id,
                        category="payment", type="payment_reminder_parent",
                        priority="normal",
                        title=f"💰 {stud_name} — to'lov",
                        body=body,
                        data={"student_id": str(sid), "amount": debt,
                              "month": today.month, "year": today.year},
                        dedupe_key=f"pay_remind:{today.year}-{today.month}:parent:{sid}",
                    )

            s.commit()
        except Exception as e:
            logger.exception("dispatch_payment_reminders.tenant.error tenant=%s err=%s", slug, e)
            s.rollback()
        finally:
            s.close()


# ─────────────────────────────────────────────────────────────────────
# 5. Qarz eslatmasi — har oy 5 da
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.event_dispatchers.dispatch_overdue_payment_reminders")
def dispatch_overdue_payment_reminders():
    """Manfiy balans → parent + admin."""
    today = date.today()
    for slug, schema in _all_tenants():
        s = _tenant_session(schema)
        try:
            rows = s.execute(text("""
                SELECT s.id, s.parent_id, s.balance, u.first_name, u.last_name
                FROM students s
                JOIN users u ON u.id = s.user_id
                WHERE s.is_active=TRUE AND s.balance < 0
            """)).all()

            admin_ids = [r[0] for r in s.execute(text(
                "SELECT id FROM users WHERE role='admin' AND is_active=TRUE"
            )).all()]

            for sid, parent_id, balance, fname, lname in rows:
                stud_name = f"{fname} {lname or ''}".strip()
                debt_str  = f"{abs(float(balance)):,.0f}".replace(",", " ")
                title = f"⚠️ Qarz: {debt_str} so'm"

                if parent_id:
                    _enqueue_sync(
                        s, slug, parent_id,
                        category="payment", type="payment_overdue",
                        priority="high", title=title,
                        body=f"<b>{stud_name}</b> uchun joriy qarz: <b>{debt_str} so'm</b>.",
                        data={"student_id": str(sid), "balance": float(balance)},
                        dedupe_key=f"overdue:{today.year}-{today.month}:parent:{sid}",
                    )
                for aid in admin_ids:
                    _enqueue_sync(
                        s, slug, aid,
                        category="payment", type="payment_overdue_admin",
                        priority="normal",
                        title=f"⚠️ {stud_name} qarz",
                        body=f"<b>{stud_name}</b> qarzi: <b>{debt_str} so'm</b>.",
                        data={"student_id": str(sid), "balance": float(balance)},
                        dedupe_key=f"overdue:{today.year}-{today.month}:admin:{aid}:{sid}",
                    )

            s.commit()
        except Exception as e:
            logger.exception("dispatch_overdue.tenant.error tenant=%s err=%s", slug, e)
            s.rollback()
        finally:
            s.close()


# ─────────────────────────────────────────────────────────────────────
# 6. Subscription warning — trial tugashi yaqin
# ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.event_dispatchers.dispatch_subscription_warning")
def dispatch_subscription_warning():
    """Trial 7 kundan kam qolgan tenantlarning adminlariga warning."""
    from datetime import timezone
    now = datetime.now(timezone.utc)
    _ensure_engine()

    with _sync_engine.connect() as conn:
        tenants = conn.execute(text("""
            SELECT slug, schema_name, name, trial_ends_at
            FROM public.tenants
            WHERE is_active=TRUE
              AND subscription_status='trial'
              AND trial_ends_at IS NOT NULL
              AND trial_ends_at <= NOW() + INTERVAL '7 days'
              AND trial_ends_at > NOW()
        """)).all()

    for slug, schema, name, trial_end in tenants:
        days_left = (trial_end - now).days
        s = _tenant_session(schema)
        try:
            admin_ids = [r[0] for r in s.execute(text(
                "SELECT id FROM users WHERE role='admin' AND is_active=TRUE"
            )).all()]

            for aid in admin_ids:
                _enqueue_sync(
                    s, slug, aid,
                    category="subscription", type="subscription_warning",
                    priority="high",
                    title=f"⏳ Trial tugashi yaqin",
                    body=(
                        f"<b>{name}</b> trial muddati <b>{days_left} kun</b> qoldi. "
                        "Iltimos, obunani tasdiqlang."
                    ),
                    data={"trial_ends_at": trial_end.isoformat(), "days_left": days_left},
                    dedupe_key=f"sub_warn:{slug}:{days_left}",
                )
            s.commit()
        except Exception as e:
            logger.exception("dispatch_subscription_warning.error slug=%s err=%s", slug, e)
            s.rollback()
        finally:
            s.close()
