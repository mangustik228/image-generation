from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from loguru import logger

from config import settings
from services.bot.handlers import get_all_routers
from services.bot.middleware import AuthMiddleware

BOT_COMMANDS = [
    BotCommand(command="start", description="Запустить бота и показать меню"),
    BotCommand(command="help", description="Показать все команды"),
    BotCommand(command="publish", description="Опубликовать изображения"),
]


async def run_bot() -> None:
    bot = Bot(token=settings.telegram.bot_token)
    dp = Dispatcher()

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    for router in get_all_routers():
        dp.include_router(router)

    await bot.set_my_commands(BOT_COMMANDS)
    logger.info("Starting bot...")
    await dp.start_polling(bot)
