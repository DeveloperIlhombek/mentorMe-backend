import bcrypt
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import unquote, parse_qsl

from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"
log = logging.getLogger(__name__)

# Tenant slug — faqat kichik harf, raqam va tire. SQL schema name'ga
# xavfsiz tarzda interpolatsiya qilish uchun ishlatiladi.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def is_valid_tenant_slug(slug: str) -> bool:
    """Tenant slug formatini tekshirish (SQL injection himoyasi)."""
    return bool(slug) and bool(_SLUG_RE.match(slug))


def tenant_schema_name(slug: str) -> str:
    """Tenant slug'dan xavfsiz schema nomi qaytaradi.
    Slug formati noto'g'ri bo'lsa ValueError ko'taradi."""
    if not is_valid_tenant_slug(slug):
        raise ValueError(f"Invalid tenant slug: {slug!r}")
    return f"tenant_{slug.replace('-', '_')}"

# TMA initData yaroqlilik muddati (replay-attack himoyasi).
# Telegram tavsiyasi: 24 soat ichida, lekin biz qattiqroq qilamiz.
TMA_INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60   # 24 soat


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _new_jti() -> str:
    """Token uchun unique ID — blacklist uchun."""
    return secrets.token_urlsafe(16)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access", "jti": _new_jti()})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_REFRESH_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": _new_jti()})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """JWT'ni tekshirib, payload qaytaradi.
    - Imzo noto'g'ri yoki token expired bo'lsa, bo'sh dict qaytaradi (legacy contract).
    - Boshqa kutilmagan xatoliklar log'ga yoziladi va bo'sh dict qaytariladi.
    """
    if not token:
        return {}
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[ALGORITHM],
            options={"verify_exp": True, "verify_signature": True},
        )
    except ExpiredSignatureError:
        return {}
    except JWTError:
        return {}
    except Exception as exc:
        log.warning("decode_token: unexpected error: %s", exc)
        return {}


def verify_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = TMA_INIT_DATA_MAX_AGE_SECONDS,
) -> Optional[dict]:
    """
    Telegram WebApp initData ni HMAC-SHA256 bilan tekshirish.

    Qaytaradi: parsed dict (user dict bilan) yoki None (yaroqsiz).

    Tekshiruvlar:
      1) hash mavjudligi
      2) HMAC-SHA256 imzo
      3) auth_date < now + 60s (kelajakdan emas)
      4) auth_date > now - max_age_seconds (eski emas — replay himoyasi)
    """
    try:
        parsed = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
        hash_value = parsed.pop("hash", None)
        if not hash_value:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed, hash_value):
            return None

        # auth_date — UNIX timestamp (replay-attack himoyasi)
        auth_date_str = parsed.get("auth_date")
        if not auth_date_str:
            return None
        try:
            auth_date = int(auth_date_str)
        except (TypeError, ValueError):
            return None

        now = int(datetime.now(timezone.utc).timestamp())
        # 60 soniya — soat farqi uchun grace period
        if auth_date > now + 60:
            return None
        if max_age_seconds > 0 and (now - auth_date) > max_age_seconds:
            return None

        result = dict(parsed)
        if "user" in result:
            result["user"] = json.loads(result["user"])
        return result
    except Exception:
        return None


def verify_click_signature(
    click_trans_id: str, service_id: str, click_paydoc_id: str,
    merchant_trans_id: str, amount: str, action: str,
    sign_time: str, sign_string: str, secret_key: str,
) -> bool:
    """Verify Click payment webhook HMAC-MD5 signature."""
    raw = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"
    computed = hashlib.md5(raw.encode()).hexdigest()
    return hmac.compare_digest(computed, sign_string)
