"""
bot/main.py

Aiogram 3 Telegram bot — asosiy kirish nuqtasi.

Ishga tushirish:
  # Polling (development — Redis shart emas):
  python run_bot.py

  # Webhook (production — FastAPI orqali):
  uvicorn app.main:app --reload
  (BOT_WEBHOOK_URL .env da bo'lsa webhook avtomatik o'rnatiladi)
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.config import settings
from bot.handlers import start, student, teacher, parent, admin

logger = logging.getLogger(__name__)


def _make_storage():
    """
    Redis mavjud va o'rnatilgan bo'lsa RedisStorage,
    aks holda MemoryStorage (development uchun yetarli).
    """
    if settings.REDIS_URL:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(settings.REDIS_URL)
            logger.info("FSM storage: Redis")
            return storage
        except Exception as e:
            logger.warning(f"Redis FSM storage o'rnatilmadi ({e}), MemoryStorage ishlatiladi")
    return MemoryStorage()


def create_bot() -> Bot:
    """Bot instance yaratish."""
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Dispatcher + barcha handler routerlarni ro'yxatdan o'tkazish."""
    dp = Dispatcher(storage=_make_storage())
    dp.include_router(start.router)
    dp.include_router(student.router)
    dp.include_router(teacher.router)
    dp.include_router(parent.router)
    dp.include_router(admin.router)
    return dp


async def main():
    """Polling rejimida ishga tushirish (development)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    bot = create_bot()
    dp  = create_dispatcher()

    me = await bot.get_me()
    logger.info(f"Bot ulandi: @{me.username} ({me.first_name})")

    # Agar webhook o'rnatilgan bo'lsa — o'chiramiz (polling bilan konflikt)
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url:
        logger.info(f"Webhook o'chirilmoqda: {webhook_info.url}")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook o'chirildi ✓")

    logger.info("Polling boshlandi... (Ctrl+C — to'xtatish)")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
