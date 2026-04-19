"""
app/core/invite_store.py

Invite kodlarini saqlash (parent linking + universal invites).
Primary:  Redis (agar REDIS_URL mavjud va ulanish muvaffaqiyatli bo'lsa)
Fallback: in-process dict (development / Redis yo'q bo'lganda)

Muammo oldini olish:
  - Redis connection har so'rovda YARATILMAYDI — bitta singleton pool ishlatiladi
  - socket_connect_timeout=1 → Redis ishlamasa 1 soniya ichida fallback'ga o'tadi
  - Connection yopiladi (aclose) har ishlatgandan keyin
  - Fallback xotira process-level — multi-worker production uchun Redis zarur

Endpoint'lar:
  - POST /students/{id}/generate-parent-link  — PRN-XXXXXX yozadi
  - POST /parent/link-invite                  — o'qib, o'chiradi
  - POST /invites/generate                    — INV-XXXXXX yozadi (rol/guruh)
  - POST /auth/register                       — o'qib, o'chiradi
  - GET  /invites/info/{code}                 — faqat o'qiydi
"""
import asyncio
import time
from typing import Optional

# ── In-memory fallback ──────────────────────────────────────────────
# key = "tenant:code", value = (payload_str, expires_at_unix)
_mem: dict[str, tuple[str, float]] = {}
_mem_lock = asyncio.Lock()

INVITE_TTL = 60 * 60 * 48   # 48 soat

# Redis singleton — birinchi muvaffaqiyatli ulanishda yaratiladi
_redis_client = None
_redis_failed = False   # Redis ishlamasligini aniqlasa — qayta urinmaymiz


def _mem_key(tenant_slug: str, code: str) -> str:
    return f"{tenant_slug}:{code}"


async def _mem_set(tenant_slug: str, code: str, payload: str) -> None:
    async with _mem_lock:
        _mem[_mem_key(tenant_slug, code)] = (payload, time.time() + INVITE_TTL)


async def _mem_get(tenant_slug: str, code: str) -> Optional[str]:
    async with _mem_lock:
        entry = _mem.get(_mem_key(tenant_slug, code))
        if not entry:
            return None
        payload, expires_at = entry
        if time.time() > expires_at:
            _mem.pop(_mem_key(tenant_slug, code), None)
            return None
        return payload


async def _mem_del(tenant_slug: str, code: str) -> None:
    async with _mem_lock:
        _mem.pop(_mem_key(tenant_slug, code), None)


# ── Redis helpers ────────────────────────────────────────────────────

def _redis_key(tenant_slug: str, code: str) -> str:
    return f"invite:{tenant_slug}:{code}"


async def _get_redis():
    """
    Singleton Redis client — birinchi chaqiruvda yaratiladi.
    Agar Redis ishlamasa — None qaytaradi (1 soniya timeout).
    """
    global _redis_client, _redis_failed

    if _redis_failed:
        return None
    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as aioredis
        from app.core.config import settings

        if not settings.REDIS_URL:
            _redis_failed = True
            return None

        client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,   # ulanish uchun max 1 soniya
            socket_timeout=1,            # operatsiya uchun max 1 soniya
        )
        # Ulanishni sinab ko'rish
        await client.ping()
        _redis_client = client
        return client

    except Exception:
        _redis_failed = True
        return None


# ── Public API ────────────────────────────────────────────────────────

async def store_invite(tenant_slug: str, code: str, payload: str) -> None:
    """
    Invite kodni saqlash.

    payload:
      - parent linking: str(student_id)   — UUID string
      - universal:      "teacher"          — rol nomi
                        "student:UUID"     — rol + guruh
    """
    r = await _get_redis()
    if r is not None:
        try:
            await r.setex(_redis_key(tenant_slug, code), INVITE_TTL, payload)
            return
        except Exception:
            pass   # Redis xato — in-memory'ga tushadi

    await _mem_set(tenant_slug, code, payload)


async def get_invite(tenant_slug: str, code: str) -> Optional[str]:
    """
    Invite kodni o'qish.
    None = topilmadi yoki muddati o'tgan.
    """
    r = await _get_redis()
    if r is not None:
        try:
            val = await r.get(_redis_key(tenant_slug, code))
            if val is not None:
                return val
            # Redis'da yo'q — in-memory'da ham tekshiramiz (store fallback bo'lgan bo'lishi mumkin)
        except Exception:
            pass

    return await _mem_get(tenant_slug, code)


async def delete_invite(tenant_slug: str, code: str) -> None:
    """
    Invite kodni o'chirish (bir martalik ishlatilgandan so'ng).
    """
    r = await _get_redis()
    if r is not None:
        try:
            await r.delete(_redis_key(tenant_slug, code))
        except Exception:
            pass

    await _mem_del(tenant_slug, code)


async def close_redis() -> None:
    """
    Dastur to'xtaganda Redis connection'ni yopish.
    FastAPI lifespan'da chaqiriladi.
    """
    global _redis_client, _redis_failed
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
    _redis_failed = False
