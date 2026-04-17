"""
app/api/v1/gamification.py

Gamifikatsiya umumiy endpointlari:
  GET /leaderboard           — haftalik/umrbod reyting
  GET /gamification/profile  — o'z profili
  GET /gamification/streak   — streak ma'lumoti
  GET /gamification/badges   — barcha yutuqlar
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_student, require_any
from app.models.tenant import Achievement, Student, User
from app.schemas import ok
from app.services import gamification as gam_svc

router = APIRouter(tags=["gamification"])


@router.get("/leaderboard")
async def get_leaderboard(
    scope:    str                   = Query("weekly", description="weekly | alltime"),
    group_id: Optional[uuid.UUID]   = Query(None),
    limit:    int                   = Query(20, ge=1, le=100),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_any),
):
    """
    Reyting ro'yxati.
    - scope=weekly  → shu hafta XP bo'yicha
    - scope=alltime → jami XP bo'yicha
    - group_id      → faqat shu guruh ichida
    """
    entries = await gam_svc.get_leaderboard(db, scope=scope, group_id=group_id, limit=limit)
    return ok(entries)


@router.get("/gamification/profile")
async def get_my_profile(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_student),
):
    """O'quvchining gamifikatsiya profili (level, XP, streak)."""
    user_id = uuid.UUID(tkn["sub"])
    stmt    = select(Student).where(Student.user_id == user_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        return ok(gam_svc.level_info(0))

    profile = await gam_svc.get_profile(db, student.id)
    return ok(profile)


@router.get("/gamification/streak")
async def get_streak(
    db:  AsyncSession = Depends(get_tenant_session),
    tkn: dict         = Depends(require_student),
):
    """Streak ma'lumoti."""
    user_id = uuid.UUID(tkn["sub"])
    stmt    = select(Student).where(Student.user_id == user_id)
    student = (await db.execute(stmt)).scalar_one_or_none()
    if not student:
        return ok({"current_streak": 0, "max_streak": 0})

    profile = await gam_svc.get_profile(db, student.id)
    return ok({
        "current_streak": profile.get("current_streak", 0),
        "max_streak":     profile.get("max_streak", 0),
        "last_activity":  profile.get("last_activity"),
    })


@router.get("/gamification/badges")
async def get_all_badges(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_any),
):
    """Barcha mavjud yutuqlar (achievements) ro'yxati."""
    stmt   = select(Achievement).where(Achievement.is_active == True)
    badges = (await db.execute(stmt)).scalars().all()
    return ok([
        {
            "id":              str(b.id),
            "slug":            b.slug,
            "name_uz":         b.name_uz,
            "name_ru":         b.name_ru,
            "description_uz":  b.description_uz,
            "icon":            b.icon,
            "xp_reward":       b.xp_reward,
            "condition_type":  b.condition_type,
            "condition_value": b.condition_value,
        }
        for b in badges
    ])
