"""
app/schemas/attendance.py
"""
import uuid
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator


class AttendanceItem(BaseModel):
    student_id:  uuid.UUID
    status:      str                    # present | absent | late | excused
    note:        Optional[str] = None   # izoh (kechikish/uzr sababi)
    arrived_at:  Optional[str] = None   # HH:MM — kechikish vaqti

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"present", "absent", "late", "excused"}
        if v not in allowed:
            raise ValueError(f"status {allowed} dan biri bo'lishi kerak")
        return v


class AttendanceBulkCreate(BaseModel):
    group_id: uuid.UUID
    date:     date
    records:  List[AttendanceItem]


class AttendanceOut(BaseModel):
    id:              uuid.UUID
    student_id:      uuid.UUID
    group_id:        uuid.UUID
    date:            date
    status:          str
    note:            Optional[str]  = None
    parent_notified: bool
    first_name:      Optional[str]  = None
    last_name:       Optional[str]  = None
    model_config     = {"from_attributes": True}


class AttendanceSummary(BaseModel):
    group_id: uuid.UUID
    date:     date
    present:  int
    absent:   int
    late:     int
    excused:  int
    total:    int
    percent:  float
