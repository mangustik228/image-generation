import tempfile
from pathlib import Path

import httpx
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


def _build_characteristics_prompt(data: dict) -> str:
    """Format gateway page data into a characteristics prompt suffix."""
    content = data.get("content", {})
    h1 = content.get("h1", "")

    lines: list[str] = []
    lines.append("Данные с сайта про изделия:")
    if h1:
        lines.append(f"Название: {h1}")

    basic = content.get("characteristics", [])
    if basic:
        lines.append("")
        lines.append("## Характеристики базовые:")
        for char in basic:
            label = char.get("label", "")
            value = char.get("value", "")
            suggestion = char.get("suggestion", {})
            suggestion_text = (
                suggestion.get("text", "") if isinstance(suggestion, dict) else ""
            )
            if suggestion_text:
                lines.append(f"- {label}: {value} ({suggestion_text})")
            else:
                lines.append(f"- {label}: {value}")

    tabs_chars = content.get("tabs", {}).get("characteristics", [])
    if tabs_chars:
        lines.append("")
        lines.append("## Характеристики расширенные")
        for section in tabs_chars:
            title = section.get("title", "")
            if title:
                lines.append(f"### {title}")
            for char in section.get("characteristics", []):
                label = char.get("label", "")
                value = char.get("value", "")
                lines.append(f"- {label}: {value}")

    return "\n".join(lines)


async def _fetch_page_characteristics(gateway_url: str, page_url: str) -> str | None:
    """Fetch page data from gateway and return formatted characteristics text."""
    url = gateway_url.rstrip("/") + "/" + page_url.lstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        return _build_characteristics_prompt(data)
    except Exception as exc:
        logger.warning(f"Failed to fetch characteristics from {url}: {exc}")
        return None


@router.message(F.text == "🎨 Отправить на генерацию")
async def handle_generation(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore
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

                tasks_with_chars = 0
                tasks_without_chars = 0

                for i, image in enumerate(images):
                    ext = Path(image.url).suffix or ".jpg"
                    local_path = tmp_path / f"image_{i}{ext}"

                    if await download_image(image.url, local_path):
                        custom_prompt = image.custom_prompt
                        if image.load_characteristics.strip().lower() == "да":
                            char_text = await _fetch_page_characteristics(
                                settings.gateway.url, image.page_url
                            )
                            if char_text:
                                custom_prompt = custom_prompt + "\n\n" + char_text
                                tasks_with_chars += 1
                            else:
                                tasks_without_chars += 1
                        else:
                            tasks_without_chars += 1

                        additional_image_path = ""
                        if image.additional_image:
                            add_ext = Path(image.additional_image).suffix or ".jpg"
                            add_local_path = tmp_path / f"image_{i}_additional{add_ext}"
                            if await download_image(
                                image.additional_image, add_local_path
                            ):
                                additional_image_path = str(add_local_path)
                            else:
                                logger.warning(
                                    f"Failed to download additional image for {image.url}: "
                                    f"{image.additional_image}"
                                )

                        tasks.append(
                            ImageTask(
                                image_path=str(local_path),
                                model_name=image.model,
                                order_number=image.order_number,
                                custom_prompt=custom_prompt,
                                position=int(image.position)
                                if image.position.isdigit()
                                else 0,
                                category=image.category,
                                page_url=image.page_url,
                                source_url=image.url,
                                additional_image_path=additional_image_path,
                            )
                        )

                logger.info(
                    f"Tasks prepared: {tasks_with_chars} with characteristics, "
                    f"{tasks_without_chars} without characteristics"
                )

                if not tasks:
                    await message.answer("⚠️ Не удалось скачать ни одного изображения")
                    return

                await message.answer(
                    f"📤 Создаю batch job для {len(tasks)} изображений..."
                )
                batch_job = batch_service.create_batch_job(tasks, user_id=user_id)

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
