"""
app/webhooks/bot.py

Telegram bot webhook FastAPI endpoint.
POST /webhook/bot  ← Telegram har bir update uchun shu endpoint'ga POST qiladi.

Singleton pattern: Bot va Dispatcher bir marta yaratiladi (lifespan da),
so'rovlar orasida qayta yaratilmaydi.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Request, Response
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


async def setup_webhook() -> None:
    """Startup'da Telegram'ga webhook URL ni bildirish."""
    from app.core.config import settings
    if not settings.BOT_TOKEN or not settings.BOT_WEBHOOK_URL:
        logger.info("BOT_WEBHOOK_URL sozlanmagan — webhook o'rnatilmadi (polling mode)")
        return
    try:
        bot = get_bot()
        await bot.set_webhook(
            url=settings.BOT_WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )
        logger.info(f"Webhook o'rnatildi: {settings.BOT_WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Webhook o'rnatishda xato: {e}")


async def teardown_webhook() -> None:
    """Shutdown'da webhook va bot sessiyasini yopish."""
    global _bot, _dp
    try:
        if _bot:
            await _bot.delete_webhook(drop_pending_updates=False)
            await _bot.session.close()
        _bot = None
        _dp  = None
        logger.info("Bot sessiyasi yopildi")
    except Exception as e:
        logger.error(f"Bot yopishda xato: {e}")


# ── Webhook endpoint ───────────────────────────────────────────────────

@router.post("/webhook/bot")
async def telegram_webhook(request: Request) -> Response:
    """Telegram update ni qabul qiladi va dispatcher ga uzatadi."""
    from app.core.config import settings
    if not settings.BOT_TOKEN:
        return Response(status_code=200)

    try:
        data   = await request.json()
        update = Update.model_validate(data)
        bot    = get_bot()
        dp     = get_dp()
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Webhook update xatosi: {e}")

    return Response(status_code=200)
