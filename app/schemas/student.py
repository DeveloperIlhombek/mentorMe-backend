"""
app/schemas/student.py
Student uchun Pydantic v2 schemalar.
"""
import uuid
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


class StudentCreate(BaseModel):
    first_name:       str            = Field(min_length=2, max_length=100)
    last_name:        Optional[str]  = None
    phone:            Optional[str]  = None
    email:            Optional[EmailStr] = None
    date_of_birth:    Optional[date] = None
    gender:           Optional[str]  = None
    parent_phone:     Optional[str]  = None
    branch_id:        Optional[uuid.UUID] = None
    notes:            Optional[str]  = None
    group_ids:        Optional[List[uuid.UUID]] = None
    # Yangi maydonlar
    payment_day:      Optional[int]   = Field(None, ge=1, le=31)
    monthly_fee:      Optional[float] = Field(None, gt=0)
    telegram_id:      Optional[int]   = None
    telegram_username:Optional[str]   = None


class StudentUpdate(BaseModel):
    first_name:       Optional[str]  = None
    last_name:        Optional[str]  = None
    phone:            Optional[str]  = None
    email:            Optional[EmailStr] = None
    date_of_birth:    Optional[date] = None
    gender:           Optional[str]  = None
    parent_phone:     Optional[str]  = None
    branch_id:        Optional[uuid.UUID] = None
    notes:            Optional[str]  = None
    is_active:        Optional[bool] = None
    # Admin only
    payment_day:      Optional[int]   = Field(None, ge=1, le=31)
    monthly_fee:      Optional[float] = Field(None, gt=0)
    is_approved:      Optional[bool]  = None
    pending_delete:   Optional[bool]  = None
    # Telegram
    telegram_id:      Optional[int]   = None
    telegram_username:Optional[str]   = None


class StudentOut(BaseModel):
    id:            uuid.UUID
    user_id:       uuid.UUID
    first_name:    str
    last_name:     Optional[str]  = None
    phone:         Optional[str]  = None
    email:         Optional[str]  = None
    balance:       float
    is_active:     bool
    enrolled_at:   Optional[date] = None
    date_of_birth: Optional[date] = None
    gender:        Optional[str]  = None
    parent_phone:  Optional[str]  = None
    notes:         Optional[str]  = None
    groups:           List[dict]    = []
    gamification:     Optional[dict] = None
    payment_day:      Optional[int]  = None
    monthly_fee:      Optional[float] = None
    is_approved:      bool            = True
    pending_delete:   bool            = False
    telegram_id:      Optional[int]  = None
    telegram_username:Optional[str]  = None
    model_config      = {"from_attributes": True}


class StudentShort(BaseModel):
    """Ro'yxat uchun qisqa ko'rinish."""
    id:         uuid.UUID
    user_id:    uuid.UUID
    first_name: str
    last_name:  Optional[str] = None
    phone:      Optional[str] = None
    balance:    float
    is_active:  bool
    model_config = {"from_attributes": True}
