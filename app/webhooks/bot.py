"""
app/webhooks/bot.py

Telegram bot webhook FastAPI endpoint.
POST /webhook/bot  ← Telegram bu endpointga update yuboradi.
"""
from fastapi import APIRouter, Request, Response
from aiogram.types import Update

router = APIRouter(tags=["webhook"])


@router.post("/webhook/bot")
async def telegram_webhook(request: Request) -> Response:
    """Telegram bot webhook."""
    from bot.main import create_bot, create_dispatcher
    from app.core.config import settings

    if not settings.BOT_TOKEN:
        return Response(status_code=200)

    bot = create_bot()
    dp  = create_dispatcher()

    data   = await request.json()
    update = Update.model_validate(data)

    await dp.feed_update(bot, update)
    await bot.session.close()

    return Response(status_code=200)
