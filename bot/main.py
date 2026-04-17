"""
bot/main.py

Aiogram 3 Telegram bot — asosiy kirish nuqtasi.
Webhook rejimida ishlaydi (FastAPI /webhook/bot endpointi orqali).

Ishga tushirish:
  # Webhook (production):
  uvicorn app.main:app  (FastAPI webhook ni qabul qiladi)

  # Polling (development):
  python -m bot.main
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.config import settings
from bot.handlers import start, student, teacher, parent, admin

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Bot instance yaratish."""
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Dispatcher yaratish — Redis FSM storage bilan."""
    # Redis mavjud bo'lsa — RedisStorage, yo'q bo'lsa — MemoryStorage
    try:
        storage = RedisStorage.from_url(settings.REDIS_URL)
    except Exception:
        logger.warning("Redis mavjud emas, MemoryStorage ishlatiladi")
        storage = MemoryStorage()

    dp = Dispatcher(storage=storage)

    # Handlerlarni ro'yxatdan o'tkazish
    dp.include_router(start.router)
    dp.include_router(student.router)
    dp.include_router(teacher.router)
    dp.include_router(parent.router)
    dp.include_router(admin.router)

    return dp


# Polling (development uchun)
async def main():
    logging.basicConfig(level=logging.INFO)
    bot = create_bot()
    dp  = create_dispatcher()

    logger.info("Bot polling rejimida ishga tushdi...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
