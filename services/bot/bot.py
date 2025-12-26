from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from loguru import logger

from config import settings
from services.bot.handlers import get_all_routers


async def run_bot() -> None:
    session = None
    if settings.telegram.proxy_url:
        session = AiohttpSession(proxy=settings.telegram.proxy_url)
        logger.info(f"Using proxy: {settings.telegram.proxy_url}")
    bot = Bot(token=settings.telegram.bot_token, session=session)
    dp = Dispatcher()

    for router in get_all_routers():
        dp.include_router(router)

    logger.info("Starting bot...")
    await dp.start_polling(bot)
