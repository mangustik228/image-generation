import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from config import settings
from services.batch import BatchService
from services.batch.batch_service import ImageTask
from services.bot.locks import generation_lock
from services.bot.utils import download_image
from services.google_sheets import GoogleSheetsService

router = Router()


@router.message(F.text == "🎨 Отправить на генерацию")
async def handle_generation(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore
    if user_id not in settings.telegram.authorized_users:
        await message.answer("⛔ Доступ запрещён")
        return

    if generation_lock.locked():
        await message.answer("⏳ Генерация уже запущена. Подождите завершения.")
        return

    async with generation_lock:
        logger.info(f"User {user_id} started image generation")

        try:
            batch_service = BatchService(
                api_key=settings.gemini.api_key,
                database_url=settings.database.url,
                model=settings.gemini.model,
            )

            pending_jobs = batch_service.get_pending_jobs()
            if pending_jobs:
                job_names = "\n".join([f"• `{j.job_name}`" for j in pending_jobs])
                await message.answer(
                    f"⚠️ *Есть незавершённые задачи ({len(pending_jobs)}):*\n\n"
                    f"{job_names}\n\n"
                    f"Дождитесь их завершения перед запуском новой генерации.",
                    parse_mode="Markdown",
                )
                return

            sheets_service = GoogleSheetsService(settings.google.credentials_path)

            images = sheets_service.get_pending_images()
            if not images:
                await message.answer("ℹ️ Нет изображений для генерации")
                return

            await message.answer(f"📥 Скачиваю {len(images)} изображений...")

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                tasks: list[ImageTask] = []

                for i, image in enumerate(images):
                    ext = Path(image.url).suffix or ".jpg"
                    local_path = tmp_path / f"image_{i}{ext}"

                    if await download_image(image.url, local_path):
                        tasks.append(
                            ImageTask(
                                image_path=str(local_path),
                                model_name=image.model,
                                order_number=image.order_number,
                                custom_prompt=image.custom_prompt,
                                position=int(image.position)
                                if image.position.isdigit()
                                else 0,
                                category=image.category,
                                page_url=image.page_url,
                                source_url=image.url,
                            )
                        )

                if not tasks:
                    await message.answer(
                        "⚠️ Не удалось скачать ни одного изображения"
                    )
                    return

                await message.answer(
                    f"📤 Создаю batch job для {len(tasks)} изображений..."
                )
                batch_job = batch_service.create_batch_job(tasks)

                logger.info(f"Batch job created: {batch_job.job_name}")
                await message.answer(
                    f"✅ *Batch job создан!*\n\n"
                    f"├ Название: `{batch_job.job_name}`\n"
                    f"├ Изображений: {len(tasks)}\n"
                    f"└ Статус: {batch_job.status}",
                    parse_mode="Markdown",
                )

        except Exception as e:
            logger.exception("Image generation failed")
            await message.answer(f"❌ Ошибка генерации: {e}")
