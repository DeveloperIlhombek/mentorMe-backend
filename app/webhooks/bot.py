"""
app/webhooks/bot.py

Telegram bot webhook FastAPI endpoint.
POST /webhook/bot  ← Telegram har bir update uchun shu endpoint'ga POST qiladi.

Singleton pattern: Bot va Dispatcher bir marta yaratiladi (lifespan da),
so'rovlar orasida qayta yaratilmaydi.

Xavfsizlik:
  - X-Telegram-Bot-Api-Secret-Token header tekshiriladi (BOT_WEBHOOK_SECRET).
  - BOT_MODE=polling bo'lsa webhook o'rnatilmaydi.
"""
import logging
import secrets

from fastapi import APIRouter, Header, Request, Response, status
from aiogram.types import Update

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

# ── Singleton ──────────────────────────────────────────────────────────
_bot = None
_dp  = None


def get_bot():
    global _bot
    if _bot is None:
        from bot.main import create_bot
        _bot = create_bot()
    return _bot


def get_dp():
    global _dp
    if _dp is None:
        from bot.main import create_dispatcher
        _dp = create_dispatcher()
    return _dp


def _resolve_mode() -> str:
    """Effektiv mode: auto = development→polling, production→webhook."""
    from app.core.config import settings
    if settings.BOT_MODE in ("webhook", "polling"):
        return settings.BOT_MODE
    return "webhook" if settings.is_production else "polling"


async def setup_webhook() -> None:
    """Startup'da Telegram'ga webhook URL ni bildirish."""
    from app.core.config import settings

    if _resolve_mode() == "polling":
        logger.info("BOT_MODE=polling — webhook o'rnatilmaydi")
        return

    if not settings.BOT_TOKEN or not settings.BOT_WEBHOOK_URL:
        logger.info("BOT_TOKEN/BOT_WEBHOOK_URL sozlanmagan — webhook skip")
        return

    try:
        bot = get_bot()
        kwargs = {
            "url": settings.BOT_WEBHOOK_URL,
            "drop_pending_updates": True,
            "allowed_updates": ["message", "callback_query", "my_chat_member"],
        }
        if settings.BOT_WEBHOOK_SECRET:
            kwargs["secret_token"] = settings.BOT_WEBHOOK_SECRET
        await bot.set_webhook(**kwargs)
        logger.info("webhook.set url=%s secret=%s",
                    settings.BOT_WEBHOOK_URL, bool(settings.BOT_WEBHOOK_SECRET))
    except Exception as e:
        logger.error("webhook.set.error err=%s", e)


async def teardown_webhook() -> None:
    """Shutdown'da webhook va bot sessiyasini yopish."""
    global _bot, _dp
    try:
        if _bot:
            await _bot.delete_webhook(drop_pending_updates=False)
            await _bot.session.close()
        _bot = None
        _dp  = None
        logger.info("webhook.teardown.ok")
    except Exception as e:
        logger.error("webhook.teardown.error err=%s", e)


# ── Webhook endpoint ───────────────────────────────────────────────────

@router.post("/webhook/bot")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    """Telegram update ni qabul qiladi va dispatcher ga uzatadi."""
    from app.core.config import settings

    if not settings.BOT_TOKEN:
        return Response(status_code=200)

    # ── Secret token validation ─────────────────────────────────────
    if settings.BOT_WEBHOOK_SECRET:
        expected = settings.BOT_WEBHOOK_SECRET
        actual   = x_telegram_bot_api_secret_token or ""
        if not secrets.compare_digest(expected, actual):
            logger.warning("webhook.secret.mismatch")
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        data   = await request.json()
        update = Update.model_validate(data)
        bot    = get_bot()
        dp     = get_dp()
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.exception("webhook.update.error err=%s", e)

    return Response(status_code=200)
