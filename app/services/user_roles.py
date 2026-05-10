"""
app/services/user_roles.py

Multi-role yordamchilar.

Asosiy g'oya:
  - Bitta `User` ko'p rolga ega bo'lishi mumkin (`user_roles` jadvali).
  - `users.role` — *default/active* rol (login qilganda yoki rol almashtirmaganda).
  - JWT'dagi `role` — joriy aktiv rol; `roles` — mavjud barcha aktiv rollar.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import User, UserRole


async def list_active_roles(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Foydalanuvchining aktiv rollar ro'yxati. Default rol (users.role)
    har doim qaytariladigan ro'yxatga qo'shiladi (legacy backfill kafolati)."""
    rows = (await db.execute(
        select(UserRole.role).where(
            UserRole.user_id == user_id,
            UserRole.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    roles = list(dict.fromkeys(rows))  # unique, tartibni saqlab

    if not roles:
        # Legacy: user_roles bo'sh bo'lsa, users.role'dan oladi
        u = (await db.execute(
            select(User.role).where(User.id == user_id)
        )).scalar_one_or_none()
        if u:
            roles = [u]
    return roles


async def has_role(db: AsyncSession, user_id: uuid.UUID, role: str) -> bool:
    roles = await list_active_roles(db, user_id)
    return role in roles


async def grant_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    role: str,
    branch_id: Optional[uuid.UUID] = None,
    granted_by: Optional[uuid.UUID] = None,
) -> UserRole:
    """Rolni qo'shish (idempotent)."""
    existing = (await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role == role,
        )
    )).scalar_one_or_none()

    if existing:
        existing.is_active = True
        if branch_id is not None:
            existing.branch_id = branch_id
        return existing

    ur = UserRole(
        user_id=user_id,
        role=role,
        branch_id=branch_id,
        is_active=True,
        granted_by=granted_by,
    )
    db.add(ur)
    return ur


async def revoke_role(db: AsyncSession, user_id: uuid.UUID, role: str) -> bool:
    """Rolni o'chirish (deaktivatsiya). Default users.role bo'lsa,
    boshqa aktiv rolga ko'chirib qo'yamiz (yo'q bo'lsa o'zgartirmaymiz)."""
    ur = (await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role == role,
        )
    )).scalar_one_or_none()
    if not ur:
        return False
    ur.is_active = False

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one()
    if user.role == role:
        # default rolni boshqasiga ko'chiramiz
        remaining = await list_active_roles(db, user_id)
        remaining = [r for r in remaining if r != role]
        if remaining:
            user.role = remaining[0]
    return True
