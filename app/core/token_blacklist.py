"""
app/core/token_blacklist.py

JWT token blacklist (logout uchun).
Primary:  Redis (TTL = token muddatigacha)
Fallback: in-process set (dev / Redis yo'q bo'lsa)

Foydalanish:
    await blacklist_token(jti, exp_unix)        # logout endpointida
    if await is_blacklisted(jti): raise ...     # get_current_token ichida
"""
import asyncio
import time
from typing import Optional


# In-memory fallback: jti → expires_at
_mem: dict[str, float] = {}
_mem_lock = asyncio.Lock()


async def _cleanup_mem() -> None:
    """Eski yozuvlarni tozalash (xotirani toldirmasin)."""
    now = time.time()
    expired = [k for k, v in _mem.items() if v < now]
    for k in expired:
        _mem.pop(k, None)


def _redis_key(jti: str) -> str:
    return f"blacklist:{jti}"


async def _get_redis():
    """invite_store dagi singleton Redis ni qayta ishlatamiz."""
    try:
        from app.core.invite_store import _get_redis
        return await _get_redis()
    except Exception:
        return None


async def blacklist_token(jti: str, exp_unix: int) -> None:
    """
    Token jti ni blacklist'ga qo'shish.
    exp_unix — token tugash vaqti (UNIX). TTL shunga moslab beriladi.
    """
    if not jti:
        return
    ttl = max(int(exp_unix - time.time()), 1)

    r = await _get_redis()
    if r is not None:
        try:
            await r.setex(_redis_key(jti), ttl, "1")
            return
        except Exception:
            pass

    async with _mem_lock:
        _mem[jti] = exp_unix
        if len(_mem) % 100 == 0:
            await _cleanup_mem()


async def is_blacklisted(jti: Optional[str]) -> bool:
    """jti blacklist'da bormi?"""
    if not jti:
        return False

    r = await _get_redis()
    if r is not None:
        try:
            val = await r.get(_redis_key(jti))
            if val is not None:
                return True
        except Exception:
            pass

    async with _mem_lock:
        exp = _mem.get(jti)
        if exp is None:
            return False
        if exp < time.time():
            _mem.pop(jti, None)
            return False
        return True
