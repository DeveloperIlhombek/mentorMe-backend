import logging
import secrets
from pydantic_settings import BaseSettings
from typing import List

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    APP_ENV:         str = "development"
    APP_SECRET_KEY:  str = "dev-secret-key-change-in-production"
    APP_NAME:        str = "EduSaaS"
    APP_VERSION:     str = "3.0.0"

    DATABASE_URL:          str = "postgresql+asyncpg://edusaas:edusaas_pass@localhost:5432/edusaas"
    DATABASE_POOL_SIZE:    int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    REDIS_URL: str = "redis://localhost:6379/0"

    # BOT_TOKEN — .env faylida bo'lishi kerak (default bo'sh — secret-leak'dan himoya).
    BOT_TOKEN:               str = ""
    BOT_WEBHOOK_URL:         str = ""          # Production: https://api.edusaas.uz/webhook/bot
    BOT_WEBHOOK_SECRET:      str = ""          # Telegram secret_token header validation
    BOT_USERNAME:            str = ""
    BOT_MODE:                str = "auto"      # auto|webhook|polling
    FRONTEND_URL:            str = "https://your-frontend.vercel.app"  # TMA URL

    TELEGRAM_RATE_LIMIT_PER_SEC:  int = 25
    NOTIF_QUIET_START:            str = "22:00"
    NOTIF_QUIET_END:              str = "07:00"
    NOTIF_LINK_TOKEN_TTL_DAYS:    int = 7
    WS_MAX_CONNECTIONS_PER_USER:  int = 3

    JWT_SECRET:                str = "dev-jwt-secret-change-in-production"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_HOURS:  int = 8

    CLICK_MERCHANT_ID: str = ""
    CLICK_SERVICE_ID:  str = ""
    CLICK_SECRET_KEY:  str = ""

    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY:   str = ""
    S3_SECRET_KEY:   str = ""
    S3_BUCKET_NAME:  str = "edusaas-files"
    S3_REGION:       str = "ru-central1"

    SENTRY_DSN: str = ""

    # MUHIM: List[str] emas — oddiy str sifatida olamiz,
    # keyin property orqali listga aylantiramiz.
    # .env da: ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    @property
    def allowed_origins_list(self) -> List[str]:
        """ALLOWED_ORIGINS stringini listga aylantiradi."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",   # .env da qo'shimcha o'zgaruvchilar bo'lsa rad etmaymiz
    }


_INSECURE_DEFAULTS = {
    "dev-secret-key-change-in-production",
    "dev-jwt-secret-change-in-production",
    "",
}


def _validate_production_secrets(s: "Settings") -> None:
    """Production muhitida default/bo'sh secretlarni rad etish."""
    if not s.is_production:
        return
    problems: list[str] = []
    if s.APP_SECRET_KEY in _INSECURE_DEFAULTS or len(s.APP_SECRET_KEY) < 32:
        problems.append("APP_SECRET_KEY (kamida 32 ta belgi bo'lishi shart)")
    if s.JWT_SECRET in _INSECURE_DEFAULTS or len(s.JWT_SECRET) < 32:
        problems.append("JWT_SECRET (kamida 32 ta belgi bo'lishi shart)")
    if not s.BOT_TOKEN:
        problems.append("BOT_TOKEN (Telegram autentifikatsiya uchun)")
    if problems:
        raise RuntimeError(
            "Production muhitida quyidagi sozlamalar to'g'ri kiritilmagan: "
            + ", ".join(problems)
        )


def _warn_dev_defaults(s: "Settings") -> None:
    """Development muhitida ham default secretlar haqida ogohlantirish.
    Har safar restartda yangi token ishlatilishini istamasak, .env yarating."""
    if s.is_production:
        return
    if s.APP_SECRET_KEY in _INSECURE_DEFAULTS:
        log.warning("⚠️  APP_SECRET_KEY default qiymatda — .env faylida o'rnating.")
    if s.JWT_SECRET in _INSECURE_DEFAULTS:
        log.warning("⚠️  JWT_SECRET default qiymatda — .env faylida o'rnating.")


settings = Settings()
_validate_production_secrets(settings)
_warn_dev_defaults(settings)
