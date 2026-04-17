"""
app/schemas/group.py
Group uchun Pydantic v2 schemalar.
"""
import uuid
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ScheduleItem(BaseModel):
    day:   int            # 1=Dushanba ... 7=Yakshanba
    start: str            # "09:00"
    end:   str            # "11:00"
    room:  Optional[str] = None


class GroupCreate(BaseModel):
    name:         str                       = Field(min_length=2, max_length=200)
    subject:      str
    branch_id:    Optional[uuid.UUID]       = None
    teacher_id:   Optional[uuid.UUID]       = None
    level:        Optional[str]             = None
    schedule:     Optional[List[ScheduleItem]] = None
    start_date:   Optional[date]            = None
    end_date:     Optional[date]            = None
    monthly_fee:  Optional[float]           = Field(None, ge=0)
    max_students: int                       = Field(15, ge=1, le=200)
    status:       str                       = "active"


class GroupUpdate(BaseModel):
    name:         Optional[str]   = None
    subject:      Optional[str]   = None
    teacher_id:   Optional[uuid.UUID] = None
    level:        Optional[str]   = None
    schedule:     Optional[List[ScheduleItem]] = None
    monthly_fee:  Optional[float] = None
    max_students: Optional[int]   = None
    status:       Optional[str]   = None


class GroupOut(BaseModel):
    id:           uuid.UUID
    name:         str
    subject:      str
    level:        Optional[str]   = None
    schedule:     Optional[List[dict]] = None
    monthly_fee:  Optional[float] = None
    max_students: int
    status:       str
    student_count:int             = 0
    teacher:      Optional[dict]  = None
    start_date:   Optional[date]  = None
    end_date:     Optional[date]  = None
    created_at:   datetime
    model_config  = {"from_attributes": True}
