from aiogram import Bot, Dispatcher
from loguru import logger

from config import settings
from services.bot.handlers import get_all_routers


async def run_bot() -> None:
    bot = Bot(token=settings.telegram.bot_token)
    dp = Dispatcher()

    for router in get_all_routers():
        dp.include_router(router)

    logger.info("Starting bot...")
    await dp.start_polling(bot)
