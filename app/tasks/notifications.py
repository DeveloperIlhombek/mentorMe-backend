import structlog
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.notifications.send_lesson_reminders")
def send_lesson_reminders():
    """Send Telegram reminders 30 minutes before lessons."""
    logger.info("task_send_lesson_reminders_started")
    # TODO: Query groups with lessons starting in 30 min, send Telegram messages
    pass


@celery_app.task(name="app.tasks.notifications.daily_attendance_reminder")
def daily_attendance_reminder():
    """Remind teachers to take attendance for today's classes."""
    logger.info("task_daily_attendance_reminder_started")
    # TODO: Query groups with schedule matching today, notify teachers
    pass


@celery_app.task(name="app.tasks.notifications.notify_absent_parents")
def notify_absent_parents(student_ids: list, group_id: str, date: str):
    """Notify parents when their child is absent."""
    logger.info("task_notify_absent_parents", count=len(student_ids), date=date)
    # TODO: For each student, find parent telegram_id and send message via bot
    pass


@celery_app.task(name="app.tasks.notifications.send_telegram_message")
def send_telegram_message(telegram_id: int, text: str, parse_mode: str = "HTML"):
    """Send a single Telegram message."""
    import httpx
    from app.core.config import settings
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            json={"chat_id": telegram_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("telegram_message_sent", telegram_id=telegram_id)
    except Exception as e:
        logger.error("telegram_message_failed", telegram_id=telegram_id, error=str(e))
