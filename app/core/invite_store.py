"""
app/core/invite_store.py

Parent invite kodlarini saqlash.
Primary: Redis (production)
Fallback: in-process dict (development / Redis yo'q bo'lganda)

Ikki endpoint ishlatadi:
  - POST /students/{id}/generate-parent-link  — yozadi
  - POST /parent/link-invite                  — o'qib, o'chiradi
"""
import time
from typing import Optional

# ── In-memory fallback ──────────────────────────────────────────────
# key = "tenant:code", value = (student_id_str, expires_at_unix)
_mem: dict[str, tuple[str, float]] = {}

INVITE_TTL = 60 * 60 * 48  # 48 soat (sekund)


def _mem_key(tenant_slug: str, code: str) -> str:
    return f"{tenant_slug}:{code}"


def _mem_set(tenant_slug: str, code: str, student_id: str) -> None:
    _mem[_mem_key(tenant_slug, code)] = (student_id, time.time() + INVITE_TTL)


def _mem_get(tenant_slug: str, code: str) -> Optional[str]:
    entry = _mem.get(_mem_key(tenant_slug, code))
    if not entry:
        return None
    student_id, expires_at = entry
    if time.time() > expires_at:
        _mem.pop(_mem_key(tenant_slug, code), None)
        return None
    return student_id


def _mem_del(tenant_slug: str, code: str) -> None:
    _mem.pop(_mem_key(tenant_slug, code), None)


# ── Redis helpers ────────────────────────────────────────────────────

def _redis_key(tenant_slug: str, code: str) -> str:
    return f"parent_invite:{tenant_slug}:{code}"


async def store_invite(tenant_slug: str, code: str, student_id: str) -> None:
    """Kodni saqlash — Redis yoki in-memory fallback."""
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.setex(_redis_key(tenant_slug, code), INVITE_TTL, student_id)
        return
    except Exception:
        pass
    # Fallback
    _mem_set(tenant_slug, code, student_id)


async def get_invite(tenant_slug: str, code: str) -> Optional[str]:
    """Kodni o'qish — Redis yoki in-memory fallback. None = topilmadi/muddati o'tgan."""
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        val = await r.get(_redis_key(tenant_slug, code))
        if val:
            return val
        # Redis'da yo'q — in-memory'da ham tekshiramiz
    except Exception:
        pass
    return _mem_get(tenant_slug, code)


async def delete_invite(tenant_slug: str, code: str) -> None:
    """Kodni o'chirish (bir martalik)."""
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.delete(_redis_key(tenant_slug, code))
    except Exception:
        pass
    _mem_del(tenant_slug, code)
