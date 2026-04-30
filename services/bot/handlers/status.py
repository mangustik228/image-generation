import asyncio

from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from config import settings
from services.batch import BatchService
from services.bot.formatters import format_status_result
from services.bot.locks import status_check_lock
from services.google_drive import GoogleDriveService

router = Router()


@router.message(F.text == "📊 Проверить задания")
async def handle_check_status(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore
    if status_check_lock.locked():
        await message.answer("⏳ Проверка статусов уже запущена. Подождите завершения.")
        return

    async with status_check_lock:
        logger.info(f"User {user_id} started status check")

        try:
            await message.answer("🔍 Проверяю статусы batch jobs...")

            batch_service = BatchService(
                api_key=settings.gemini.api_key,
                database_url=settings.database.url,
                model=settings.gemini.model,
            )

            drive_service = GoogleDriveService(
                folder_id=settings.google.drive_folder_id,
            )

            # Проверяем и скачиваем результаты для PENDING и RUNNING jobs
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: batch_service.check_and_download_results(drive_service),
            )

            # Получаем общую статистику и добавляем данные о текущей обработке
            overall_stats = await asyncio.get_event_loop().run_in_executor(
                None,
                batch_service.get_overall_statistics,
            )

            # Переносим статистику текущей обработки в overall_stats
            overall_stats.current_images_succeeded = result.current_images_succeeded
            overall_stats.current_images_failed = result.current_images_failed
            overall_stats.errors_grouped = result.errors_grouped

            await message.answer(
                format_status_result(overall_stats, show_current=True),
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.exception("Status check failed")
            await message.answer(f"❌ Ошибка проверки статусов: {e}")
