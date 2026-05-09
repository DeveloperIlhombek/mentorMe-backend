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
        "app.tasks.event_dispatchers",
        "app.tasks.broadcast",
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

    # ── Notification dispatchers ──────────────────────────────────
    # Har 5 minutda — 30 minutdan keyin boshlanadigan darslar
    "dispatch-lesson-reminders": {
        "task": "app.tasks.event_dispatchers.dispatch_lesson_reminders",
        "schedule": crontab(minute="*/5"),
    },
    # Davomat eslatmasi — 3 marta kuniga
    "dispatch-attendance-pending-morning": {
        "task": "app.tasks.event_dispatchers.dispatch_attendance_pending_reminder",
        "schedule": crontab(hour=9, minute=30),
    },
    "dispatch-attendance-pending-afternoon": {
        "task": "app.tasks.event_dispatchers.dispatch_attendance_pending_reminder",
        "schedule": crontab(hour=14, minute=0),
    },
    "dispatch-attendance-pending-evening": {
        "task": "app.tasks.event_dispatchers.dispatch_attendance_pending_reminder",
        "schedule": crontab(hour=18, minute=0),
    },
    # Baholash deadline eslatmasi
    "dispatch-progress-deadline": {
        "task": "app.tasks.event_dispatchers.dispatch_progress_deadline_reminder",
        "schedule": crontab(hour=9, minute=0),
    },
    # To'lov eslatmasi — har oy 25 kuni
    "dispatch-payment-reminders": {
        "task": "app.tasks.event_dispatchers.dispatch_payment_reminders",
        "schedule": crontab(hour=9, minute=0, day_of_month=25),
    },
    # Qarz eslatmasi — har oy 5 kuni
    "dispatch-overdue-reminders": {
        "task": "app.tasks.event_dispatchers.dispatch_overdue_payment_reminders",
        "schedule": crontab(hour=9, minute=0, day_of_month=5),
    },
    # Subscription warning — har kuni 10:00
    "dispatch-subscription-warning": {
        "task": "app.tasks.event_dispatchers.dispatch_subscription_warning",
        "schedule": crontab(hour=10, minute=0),
    },
    # Quiet-hours scheduled flush — har minut zaxira
    "flush-scheduled": {
        "task": "app.tasks.notifications.flush_scheduled",
        "schedule": crontab(minute="*"),
    },

    # ── Mavjud reminderlar (legacy fallback) ──────────────────────
    "monthly-reports": {
        "task": "app.tasks.reports.generate_monthly_reports",
        "schedule": crontab(hour=6, minute=0, day_of_month=1),
    },
}
