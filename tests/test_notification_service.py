"""
Notification service unit testlari.

pytest backend/tests/test_notification_service.py

Faqat sof Python logikani tekshiradi (DB/Redis/Celery mocked).
"""
from datetime import datetime, time, timedelta, timezone

from app.services.notification_service import (
    CRITICAL_CATEGORIES,
    VALID_CATEGORIES,
    VALID_PRIORITIES,
    _in_quiet_hours,
    _next_quiet_end,
)


def test_critical_categories_subset():
    assert CRITICAL_CATEGORIES.issubset(VALID_CATEGORIES)


def test_priorities():
    assert {"low", "normal", "high", "critical"} == VALID_PRIORITIES


def test_quiet_hours_overnight():
    """22:00–07:00 — kun chegarasidan o'tadi."""
    now = datetime(2026, 5, 9, 23, 30, tzinfo=timezone.utc)
    assert _in_quiet_hours(now, time(22, 0), time(7, 0))

    now = datetime(2026, 5, 9, 6, 30, tzinfo=timezone.utc)
    assert _in_quiet_hours(now, time(22, 0), time(7, 0))

    now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
    assert not _in_quiet_hours(now, time(22, 0), time(7, 0))


def test_quiet_hours_normal_range():
    """13:00–14:00 (lunch) — bir kun ichida."""
    now = datetime(2026, 5, 9, 13, 30, tzinfo=timezone.utc)
    assert _in_quiet_hours(now, time(13, 0), time(14, 0))

    now = datetime(2026, 5, 9, 14, 30, tzinfo=timezone.utc)
    assert not _in_quiet_hours(now, time(13, 0), time(14, 0))


def test_quiet_hours_none():
    now = datetime(2026, 5, 9, 23, 0, tzinfo=timezone.utc)
    assert not _in_quiet_hours(now, None, None)


def test_next_quiet_end_today():
    now = datetime(2026, 5, 9, 6, 0, tzinfo=timezone.utc)
    nxt = _next_quiet_end(now, time(7, 0))
    assert nxt == datetime(2026, 5, 9, 7, 0, tzinfo=timezone.utc)


def test_next_quiet_end_tomorrow():
    """Soat 8:00 da quiet end 7:00 — ertaga 7:00."""
    now = datetime(2026, 5, 9, 8, 0, tzinfo=timezone.utc)
    nxt = _next_quiet_end(now, time(7, 0))
    assert nxt == datetime(2026, 5, 10, 7, 0, tzinfo=timezone.utc)
