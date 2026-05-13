"""
Фоновая задача: периодически (каждые 2 минуты) проверяет статусы batch jobs у Gemini,
скачивает результаты для завершённых, и отправляет Telegram-уведомления
пользователю, который запустил задачу.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot
from loguru import logger

from config import settings
from services.batch import BatchService
from services.bot.locks import status_check_lock
from services.google_drive import GoogleDriveService

# Интервал проверки в секундах
CHECK_INTERVAL_SECONDS = 120


def _format_notification(info: dict) -> str:
    status = info["status"]
    job_name = info["job_name"]
    total = info["total_images"]
    succeeded = info["succeeded"]
    failed = info["failed"]

    if status == "SUCCEEDED":
        header = "✅ *Batch job завершён!*"
    elif status == "FAILED":
        header = "❌ *Batch job завершился с ошибкой*"
    else:  # CANCELLED
        header = "🚫 *Batch job отменён*"

    lines = [
        header,
        "",
        f"├ Название: `{job_name}`",
        f"├ Всего изображений: {total}",
        f"├ ✅ Успешно: {succeeded}",
        f"└ ❌ С ошибками: {failed}",
    ]
    err = info.get("error_message")
    if err:
        err_short = err[:300]
        lines += ["", f"_Ошибка: {err_short}_"]
    return "\n".join(lines)


async def _run_check_once(bot: Bot) -> None:
    """Один цикл: проверить статусы и разослать уведомления."""
    if status_check_lock.locked():
        logger.debug("Status check is already running, skipping background tick")
        return

    async with status_check_lock:
        loop = asyncio.get_event_loop()
        try:
            batch_service = BatchService(
                api_key=settings.gemini.api_key,
                database_url=settings.database.url,
                model=settings.gemini.model,
            )
            drive_service = GoogleDriveService(
                folder_id=settings.google.drive_folder_id,
            )

            # Обновляем статусы и скачиваем результаты завершённых jobs
            await loop.run_in_executor(
                None,
                lambda: batch_service.check_and_download_results(drive_service),
            )

            # Достаём завершённые но ещё не уведомлённые jobs
            finished = await loop.run_in_executor(
                None, batch_service.pop_finished_unnotified_jobs
            )
        except Exception as e:
            # Не падаем — продолжим в следующий тик. invalid_grant и пр. логируем.
            logger.exception(f"Background status check failed: {e}")
            return

    for info in finished:
        user_id = info["user_id"]
        text = _format_notification(info)
        try:
            await bot.send_message(user_id, text, parse_mode="Markdown")
            logger.info(
                f"Notified user {user_id} about job {info['job_name']} "
                f"(status={info['status']})"
            )
        except Exception as e:
            logger.exception(
                f"Failed to send notification to user {user_id} "
                f"for job {info['job_name']}: {e}"
            )


async def status_watcher(bot: Bot) -> None:
    """Бесконечный цикл фоновой проверки."""
    logger.info(
        f"Status watcher started, interval = {CHECK_INTERVAL_SECONDS}s"
    )
    # Небольшая задержка перед первым тиком, чтобы бот успел подняться
    await asyncio.sleep(10)
    while True:
        await _run_check_once(bot)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
