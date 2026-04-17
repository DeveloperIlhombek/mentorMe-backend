import structlog
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()

# XP rewards config
XP_REWARDS = {
    "lesson_attended": 10,
    "lesson_completed": 20,
    "test_submitted": 20,
    "high_score_bonus": 30,    # 80%+
    "perfect_score_bonus": 50, # 100%
    "streak_7_days": 100,
    "streak_30_days": 500,
}

# Level thresholds
LEVEL_THRESHOLDS = {
    1: 0, 2: 100, 3: 300, 4: 600, 5: 1000,
    6: 1500, 7: 2200, 8: 3000, 9: 4000, 10: 5500,
}


def calculate_level(total_xp: int) -> int:
    """Calculate level from total XP."""
    level = 1
    for lvl, threshold in sorted(LEVEL_THRESHOLDS.items(), reverse=True):
        if total_xp >= threshold:
            level = lvl
            break
    return level


@celery_app.task(name="app.tasks.gamification.reset_weekly_xp")
def reset_weekly_xp():
    """Reset weekly XP leaderboard every Monday at 00:00."""
    import redis
    from app.core.config import settings
    from datetime import datetime, timezone

    logger.info("task_reset_weekly_xp_started")
    r = redis.from_url(settings.REDIS_URL)

    # Archive previous week leaderboard keys
    # In production: iterate all tenant leaderboard keys
    # Pattern: leaderboard:{tenant_slug}:weekly
    # This is a placeholder — full implementation requires tenant list
    logger.info("task_reset_weekly_xp_completed")


@celery_app.task(name="app.tasks.gamification.award_xp")
def award_xp(tenant_slug: str, student_id: str, amount: int, reason: str, reference_id: str = None):
    """Award XP to a student and update leaderboard."""
    logger.info("award_xp", tenant=tenant_slug, student=student_id, xp=amount, reason=reason)
    # TODO: Update gamification_profiles, insert xp_transaction, update Redis sorted set
    pass
