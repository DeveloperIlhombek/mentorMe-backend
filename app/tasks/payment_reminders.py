import structlog
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.payment_reminders.monthly_payment_reminder")
def monthly_payment_reminder():
    """Send payment reminder on 25th of each month for next month."""
    logger.info("task_monthly_payment_reminder_started")
    # TODO: Query all active students, send Telegram reminder for next month payment
    pass


@celery_app.task(name="app.tasks.payment_reminders.overdue_payment_reminder")
def overdue_payment_reminder():
    """Send overdue payment reminder on 5th of each month."""
    logger.info("task_overdue_payment_reminder_started")
    # TODO: Query students with negative balance, send reminder
    pass
