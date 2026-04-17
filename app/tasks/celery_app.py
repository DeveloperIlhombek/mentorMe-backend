"""
app/tasks/celery_app.py

Celery konfiguratsiyasi.
Redis broker va backend sifatida ishlatiladi.

Ishga tushirish:
  celery -A app.tasks.celery_app worker --loglevel=info
  celery -A app.tasks.celery_app beat --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "edusaas",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.gamification",
        "app.tasks.notifications",
        "app.tasks.reminders",
        "app.tasks.reports",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Tashkent",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ── Scheduled tasks (Celery Beat) ────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Har dushanba 00:00 — haftalik XP reset
    "calculate-churn-daily": {
        "task": "tasks.calculate_churn_risks_daily",
        "schedule": crontab(minute=0, hour=2),
    },
    "calculate-kpi-daily": {
        "task": "tasks.calculate_kpi_daily",
        "schedule": crontab(minute=0, hour=7),
    },
    "reset-weekly-xp": {
        "task": "app.tasks.gamification.reset_weekly_xp",
        "schedule": crontab(hour=0, minute=0, day_of_week=1),
    },
    # Har kuni 08:00 — dars eslatmasi
    "daily-attendance-reminder": {
        "task": "app.tasks.reminders.daily_attendance_reminder",
        "schedule": crontab(hour=8, minute=0),
    },
    # Har oyning 25-kuni — to'lov eslatmasi
    "monthly-payment-reminder": {
        "task": "app.tasks.reminders.monthly_payment_reminder",
        "schedule": crontab(hour=9, minute=0, day_of_month=25),
    },
    # Har oyning 1-kuni — oylik hisobot
    "monthly-reports": {
        "task": "app.tasks.reports.generate_monthly_reports",
        "schedule": crontab(hour=6, minute=0, day_of_month=1),
    },
    # Har oyning 5-kuni — qarz eslatmasi
    "overdue-payment-reminder": {
        "task": "app.tasks.reminders.overdue_payment_reminder",
        "schedule": crontab(hour=9, minute=0, day_of_month=5),
    },
}
