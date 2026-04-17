"""
app/services/gamification.py

Gamifikatsiya:
  - XP berish + streak hisoblash
  - Redis Sorted Set leaderboard (haftalik + umrbod)
  - Achievement tekshirish va berish
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import (
    Achievement,
    GamificationProfile,
    Student,
    StudentAchievement,
    User,
    XpTransaction,
)

XP_LEVELS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500]
XP_VALUES  = {
    "lesson_attended":  10,
    "lesson_completed": 20,
    "test_submitted":   20,
    "high_score_bonus": 30,
    "perfect_score":    50,
    "streak_7":        100,
    "streak_30":       500,
}


def _get_redis():
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings
        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None


def _calc_level(total_xp: int) -> int:
    level = 1
    for i, threshold in enumerate(XP_LEVELS):
        if total_xp >= threshold:
            level = i + 1
    return min(level, 10)


def level_info(total_xp: int) -> dict:
    level = _calc_level(total_xp)
    cur   = XP_LEVELS[level - 1]
    nxt   = XP_LEVELS[level] if level < 10 else XP_LEVELS[-1]
    pct   = (total_xp - cur) / (nxt - cur) * 100 if nxt > cur else 100.0
    return {
        "level": level, "total_xp": total_xp,
        "current_threshold": cur, "next_threshold": nxt,
        "progress_percent": round(pct, 1),
        "xp_needed": max(0, nxt - total_xp),
    }


async def award_xp(
    db: AsyncSession,
    student_id: uuid.UUID,
    amount: int,
    reason: str,
    reference_id: Optional[uuid.UUID] = None,
    tenant_slug: Optional[str] = None,
) -> dict:
    """XP berish: tranzaksiya + profil yangilash + Redis."""
    db.add(XpTransaction(student_id=student_id, amount=amount, reason=reason, reference_id=reference_id))

    stmt    = select(GamificationProfile).where(GamificationProfile.student_id == student_id)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if not profile:
        profile = GamificationProfile(student_id=student_id)
        db.add(profile)
        await db.flush()

    profile.total_xp  += amount
    profile.weekly_xp += amount
    profile.current_level = _calc_level(profile.total_xp)

    today = date.today()
    if profile.last_activity_date:
        diff = (today - profile.last_activity_date).days
        if diff == 1:
            profile.current_streak += 1
            profile.max_streak = max(profile.max_streak, profile.current_streak)
        elif diff > 1:
            profile.current_streak = 1
    else:
        profile.current_streak = 1
    profile.last_activity_date = today

    if tenant_slug:
        redis = _get_redis()
        if redis:
            try:
                async with redis as r:
                    sid = str(student_id)
                    await r.zadd(f"leaderboard:weekly:{tenant_slug}",  {sid: profile.weekly_xp})
                    await r.zadd(f"leaderboard:alltime:{tenant_slug}", {sid: profile.total_xp})
                    await r.expire(f"leaderboard:weekly:{tenant_slug}", 8 * 24 * 3600)
            except Exception:
                pass

    return {"awarded": amount, "total_xp": profile.total_xp,
            "level": profile.current_level, "streak": profile.current_streak}


async def get_profile(db: AsyncSession, student_id: uuid.UUID) -> dict:
    stmt    = select(GamificationProfile).where(GamificationProfile.student_id == student_id)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if not profile:
        return level_info(0) | {"current_streak": 0, "max_streak": 0, "weekly_xp": 0}
    info = level_info(profile.total_xp)
    info.update({
        "current_streak": profile.current_streak, "max_streak": profile.max_streak,
        "weekly_xp": profile.weekly_xp,
        "last_activity_date": profile.last_activity_date.isoformat() if profile.last_activity_date else None,
    })
    return info


async def get_xp_history(db: AsyncSession, student_id: uuid.UUID, limit: int = 20) -> List[dict]:
    stmt = select(XpTransaction).where(XpTransaction.student_id == student_id).order_by(XpTransaction.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": str(r.id), "amount": r.amount, "reason": r.reason, "created_at": r.created_at.isoformat()} for r in rows]


async def get_leaderboard(
    db: AsyncSession,
    scope: str = "weekly",
    group_id: Optional[uuid.UUID] = None,
    limit: int = 20,
    tenant_slug: Optional[str] = None,
) -> List[dict]:
    """Reyting. Redis mavjud bo'lsa undan, yo'q bo'lsa DB dan."""
    if tenant_slug and not group_id:
        redis = _get_redis()
        if redis:
            try:
                key = f"leaderboard:{scope}:{tenant_slug}"
                async with redis as r:
                    entries = await r.zrevrange(key, 0, limit - 1, withscores=True)
                if entries:
                    result = []
                    for rank, (sid_str, score) in enumerate(entries, start=1):
                        sid  = uuid.UUID(sid_str)
                        row  = (await db.execute(select(Student, User).join(User, Student.user_id == User.id).where(Student.id == sid))).first()
                        if row:
                            st, u = row
                            result.append({"rank": rank, "student_id": sid_str, "first_name": u.first_name,
                                           "last_name": u.last_name, "avatar_url": u.avatar_url,
                                           "xp": int(score), "current_level": _calc_level(int(score))})
                    return result
            except Exception:
                pass

    # DB fallback
    from app.models.tenant import StudentGroup
    order_col = GamificationProfile.weekly_xp if scope == "weekly" else GamificationProfile.total_xp
    stmt = (select(GamificationProfile, Student, User)
            .join(Student, GamificationProfile.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .where(Student.is_active == True)
            .order_by(desc(order_col)).limit(limit))
    if group_id:
        stmt = stmt.join(StudentGroup, and_(StudentGroup.student_id == Student.id, StudentGroup.group_id == group_id, StudentGroup.is_active == True))
    rows = (await db.execute(stmt)).all()
    return [{"rank": rank, "student_id": str(st.id), "first_name": u.first_name, "last_name": u.last_name,
             "avatar_url": u.avatar_url, "xp": profile.weekly_xp if scope == "weekly" else profile.total_xp,
             "total_xp": profile.total_xp, "weekly_xp": profile.weekly_xp,
             "current_streak": profile.current_streak, "current_level": profile.current_level}
            for rank, (profile, st, u) in enumerate(rows, start=1)]


async def reset_weekly_xp(db: AsyncSession, tenant_slug: str) -> int:
    """Har dushanba 00:00 — haftalik XP reset."""
    result = await db.execute(update(GamificationProfile).values(weekly_xp=0, weekly_reset_at=datetime.utcnow()))
    await db.commit()
    redis = _get_redis()
    if redis:
        try:
            async with redis as r:
                await r.delete(f"leaderboard:weekly:{tenant_slug}")
        except Exception:
            pass
    return result.rowcount


async def check_and_award_achievements(db: AsyncSession, student_id: uuid.UUID) -> List[str]:
    stmt    = select(GamificationProfile).where(GamificationProfile.student_id == student_id)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if not profile:
        return []
    earned_ids  = {row[0] for row in (await db.execute(select(StudentAchievement.achievement_id).where(StudentAchievement.student_id == student_id))).all()}
    achievements = (await db.execute(select(Achievement).where(Achievement.is_active == True))).scalars().all()
    new_awards = []
    for ach in achievements:
        if ach.id in earned_ids:
            continue
        earned = (ach.condition_type == "streak" and profile.current_streak >= ach.condition_value) or (ach.condition_type == "xp" and profile.total_xp >= ach.condition_value)
        if earned:
            db.add(StudentAchievement(student_id=student_id, achievement_id=ach.id))
            if ach.xp_reward > 0:
                await award_xp(db, student_id, ach.xp_reward, f"achievement_{ach.slug}")
            new_awards.append(ach.slug)
    if new_awards:
        await db.commit()
    return new_awards
