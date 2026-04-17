from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_ENV:         str = "development"
    APP_SECRET_KEY:  str = "dev-secret-key-change-in-production"
    APP_NAME:        str = "EduSaaS"
    APP_VERSION:     str = "3.0.0"

    DATABASE_URL:          str = "postgresql+asyncpg://edusaas:edusaas_pass@localhost:5432/edusaas"
    DATABASE_POOL_SIZE:    int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    REDIS_URL: str = "redis://localhost:6379/0"

    BOT_TOKEN:       str = ""
    BOT_WEBHOOK_URL: str = ""

    JWT_SECRET:                str = "dev-jwt-secret-change-in-production"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS:   int = 30

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
