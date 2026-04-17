"""
app/schemas/gamification.py
"""
import uuid
from datetime import date
from typing import Optional
from pydantic import BaseModel


class GamificationOut(BaseModel):
    id:                 uuid.UUID
    total_xp:           int
    current_level:      int
    current_streak:     int
    max_streak:         int
    weekly_xp:          int
    last_activity_date: Optional[date] = None
    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank:           int
    student_id:     uuid.UUID
    first_name:     str
    last_name:      Optional[str] = None
    avatar_url:     Optional[str] = None
    total_xp:       int
    weekly_xp:      int
    current_streak: int
    current_level:  int
