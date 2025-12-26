from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from config import settings
from services.bot.formatters import format_stats
from services.bot.locks import parsing_lock
from services.google_sheets import GoogleSheetsService
from services.parser import Parser

router = Router()


@router.message(F.text == "🔄 Обновить изображения")
async def handle_update(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore
    if user_id not in settings.telegram.authorized_users:
        await message.answer("⛔ Доступ запрещён")
        return

    if parsing_lock.locked():
        await message.answer("⏳ Парсинг уже запущен. Подождите завершения.")
        return

    async with parsing_lock:
        await message.answer("🚀 Запускаю парсинг...")
        logger.info(f"User {user_id} started parsing")

        try:
            parser = Parser(settings.start_url)
            items, stats = await parser.parse("test")

            sheets_service = GoogleSheetsService(settings.google.credentials_path)
            items = sheets_service.populate_order_numbers(items)
            added_count = sheets_service.write_results(items)

            logger.info(f"Parsing completed. Added {added_count} items")
            await message.answer(
                format_stats(stats, added_count), parse_mode="Markdown"
            )

        except Exception as e:
            logger.exception("Parsing failed")
            await message.answer(f"❌ Ошибка парсинга: {e}")
