"""
app/schemas/auth.py
Auth endpointlar uchun schemalar.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr


class TelegramAuthRequest(BaseModel):
    init_data:   str
    tenant_slug: str


class WebLoginRequest(BaseModel):
    email:       EmailStr
    password:    str
    tenant_slug: str


class WebRegisterRequest(BaseModel):
    email:       EmailStr
    password:    str
    first_name:  str
    last_name:   Optional[str] = None
    tenant_slug: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    user_id:       str
    role:          str
    tenant_slug:   str


class RefreshRequest(BaseModel):
    refresh_token: str
