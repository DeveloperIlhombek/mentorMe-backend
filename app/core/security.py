import bcrypt
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import unquote, parse_qsl

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return {}


def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """Verify Telegram WebApp initData with HMAC-SHA256."""
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
