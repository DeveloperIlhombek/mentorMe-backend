"""
app/schemas/payment.py
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    student_id:     uuid.UUID
    group_id:       Optional[uuid.UUID] = None
    amount:         float               = Field(gt=0)
    payment_method: str                 = "cash"          # cash | click
    payment_type:   str                 = "subscription"  # subscription | debt_payment | advance
    period_month:   Optional[int]       = Field(None, ge=1, le=12)
    period_year:    Optional[int]       = Field(None, ge=2020)
    note:           Optional[str]       = None


class PaymentOut(BaseModel):
    id:             uuid.UUID
    student_id:     uuid.UUID
    amount:         float
    currency:       str
    payment_type:   str
    payment_method: str
    status:         str
    period_month:   Optional[int]      = None
    period_year:    Optional[int]      = None
    note:           Optional[str]      = None
    paid_at:        Optional[datetime] = None
    created_at:     datetime
    student:        Optional[dict]     = None
    model_config    = {"from_attributes": True}
