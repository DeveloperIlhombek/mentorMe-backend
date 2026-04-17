from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid


class TenantCreate(BaseModel):
    name: str
    slug: str
    owner_telegram_id: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    plan_id: Optional[uuid.UUID] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    brand_color: Optional[str] = None
    click_merchant_id: Optional[str] = None
    click_service_id: Optional[str] = None


class TenantResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    schema_name: str
    subscription_status: str
    trial_ends_at: Optional[datetime] = None
    is_active: bool
    brand_color: str
    created_at: datetime

    model_config = {"from_attributes": True}
