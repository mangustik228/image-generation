import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from loguru import logger

from config import settings
from services.batch import BatchService
from services.bot.formatters import format_status_result
from services.bot.locks import (
    generation_lock,
    parsing_lock,
    publish_lock,
    status_check_lock,
)
from services.google_drive import GoogleDriveService

router = Router()


async def _handle_parse(callback: CallbackQuery) -> None:
    from services.bot.formatters import format_stats
    from services.google_sheets import GoogleSheetsService
    from services.parser import Parser

    assert isinstance(callback.message, Message)

    if parsing_lock.locked():
        await callback.message.answer("⏳ Парсинг уже запущен. Подождите завершения.")
        return

    async with parsing_lock:
        await callback.message.answer("🚀 Запускаю парсинг...")
        user_id = callback.from_user.id
        logger.info(f"User {user_id} started parsing via inline")

        try:
            parser = Parser(settings.start_url)
            items, stats = await parser.parse("test")

            sheets_service = GoogleSheetsService(settings.google.credentials_path)
            items = sheets_service.populate_order_numbers(items)
            added_count = sheets_service.write_results(items)

            logger.info(f"Parsing completed. Added {added_count} items")
            await callback.message.answer(
                format_stats(stats, added_count), parse_mode="Markdown"
            )

        except Exception as e:
            logger.exception("Parsing failed")
            await callback.message.answer(f"❌ Ошибка парсинга: {e}")


async def _handle_generate(callback: CallbackQuery) -> None:
    import tempfile
    from pathlib import Path

    from services.batch.batch_service import ImageTask
    from services.bot.utils import download_image
    from services.google_sheets import GoogleSheetsService

    assert isinstance(callback.message, Message)

    if generation_lock.locked():
        await callback.message.answer(
            "⏳ Генерация уже запущена. Подождите завершения."
        )
        return

    async with generation_lock:
        user_id = callback.from_user.id
        logger.info(f"User {user_id} started image generation via inline")

        try:
            batch_service = BatchService(
                api_key=settings.gemini.api_key,
                database_url=settings.database.url,
                model=settings.gemini.model,
            )

            pending_jobs = batch_service.get_pending_jobs()
            if pending_jobs:
                job_names = "\n".join([f"• `{j.job_name}`" for j in pending_jobs])
                await callback.message.answer(
                    f"⚠️ *Есть незавершённые задачи ({len(pending_jobs)}):*\n\n"
                    f"{job_names}\n\n"
                    f"Дождитесь их завершения перед запуском новой генерации.",
                    parse_mode="Markdown",
                )
                return

            sheets_service = GoogleSheetsService(settings.google.credentials_path)

            images = sheets_service.get_pending_images()
            if not images:
                await callback.message.answer("ℹ️ Нет изображений для генерации")
                return

            await callback.message.answer(f"📥 Скачиваю {len(images)} изображений...")

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
                    await callback.message.answer(
                        "⚠️ Не удалось скачать ни одного изображения"
                    )
                    return

                await callback.message.answer(
                    f"📤 Создаю batch job для {len(tasks)} изображений..."
                )
                batch_job = batch_service.create_batch_job(tasks)

                logger.info(f"Batch job created: {batch_job.job_name}")
                await callback.message.answer(
                    f"✅ *Batch job создан!*\n\n"
                    f"├ Название: `{batch_job.job_name}`\n"
                    f"├ Изображений: {len(tasks)}\n"
                    f"└ Статус: {batch_job.status}",
                    parse_mode="Markdown",
                )

        except Exception as e:
            logger.exception("Image generation failed")
            await callback.message.answer(f"❌ Ошибка генерации: {e}")


async def _handle_status(callback: CallbackQuery) -> None:
    assert isinstance(callback.message, Message)

    if status_check_lock.locked():
        await callback.message.answer(
            "⏳ Проверка статусов уже запущена. Подождите завершения."
        )
        return

    async with status_check_lock:
        user_id = callback.from_user.id
        logger.info(f"User {user_id} started status check via inline")

        try:
            await callback.message.answer("🔍 Проверяю статусы batch jobs...")

            batch_service = BatchService(
                api_key=settings.gemini.api_key,
                database_url=settings.database.url,
                model=settings.gemini.model,
            )

            drive_service = GoogleDriveService(
                folder_id=settings.google.drive_folder_id,
            )

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: batch_service.check_and_download_results(drive_service),
            )

            overall_stats = await asyncio.get_event_loop().run_in_executor(
                None,
                batch_service.get_overall_statistics,
            )

            overall_stats.current_images_succeeded = result.current_images_succeeded
            overall_stats.current_images_failed = result.current_images_failed
            overall_stats.errors_grouped = result.errors_grouped

            await callback.message.answer(
                format_status_result(overall_stats, show_current=True),
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.exception("Status check failed")
            await callback.message.answer(f"❌ Ошибка проверки статусов: {e}")


async def _handle_publish(callback: CallbackQuery) -> None:
    from slugify import slugify

    from models.models import BatchJobImage, get_session_maker
    from services.gateway import GatewayClient
    from services.google_sheets import GoogleSheetsService
    from services.image_description import ImageDescriptionService
    from services.sync import SyncService, extract_product_markdown

    assert isinstance(callback.message, Message)

    if publish_lock.locked():
        await callback.message.answer(
            "⏳ Публикация уже запущена. Подождите завершения."
        )
        return

    async with publish_lock:
        user_id = callback.from_user.id
        logger.info(f"User {user_id} started image publishing via inline")

        try:
            await callback.message.answer("📤 Начинаю загрузку фотографий...")

            drive_service = GoogleDriveService(
                folder_id=settings.google.drive_folder_id,
            )
            session_maker = get_session_maker(settings.database.url)
            image_desc_service = ImageDescriptionService()

            sync_service = SyncService(
                database_url=settings.database.url,
                gateway_url=settings.gateway.url,
            )

            await callback.message.answer("🔄 Синхронизация с Gateway...")
            result = await sync_service.sync_files(drive_service, check_deleted=True)

            logger.info(
                f"Синхронизация: {result.requests_success} успешных, {result.requests_failed} ошибок"
            )

            descriptions_generated = 0
            for response_data in result.responses:
                content = response_data.get("content", {})
                model = content.get("model", "Unknown")
                model_slug = slugify(model, lowercase=True)

                markdown = extract_product_markdown(response_data)

                with session_maker() as session:
                    images = (
                        session.query(BatchJobImage)
                        .filter(BatchJobImage.status == "SUCCEEDED")
                        .filter(BatchJobImage.result_file.isnot(None))
                        .filter(BatchJobImage.published.is_(False))
                        .all()
                    )

                    model_images = [
                        img
                        for img in images
                        if slugify(img.model_name, lowercase=True) == model_slug
                    ]

                    if not model_images:
                        continue

                    images_without_desc = [
                        img
                        for img in model_images
                        if not (img.title and img.description)
                    ]

                    if not images_without_desc:
                        continue

                    photos: list[bytes] = []
                    image_ids: list[str] = []
                    filenames: list[str] = []

                    for img in images_without_desc:
                        if not img.result_file:
                            continue
                        if not drive_service.check_file_exists(img.result_file):
                            logger.warning(
                                f"Файл {img.result_file} (id={img.id}, model={img.model_name}) не найден на Google Drive, пропускаем"
                            )
                            continue
                        logger.info(
                            f"Загружаем файл: model={img.model_name}, source={img.source_image_name}, "
                            f"original_path={img.original_image_path}"
                        )
                        photo_bytes = drive_service.download_file(img.result_file)
                        if photo_bytes:
                            photos.append(photo_bytes)
                            image_ids.append(img.id)
                            filenames.append(f"{img.model_name}_{img.id}")

                    if not photos:
                        continue

                    try:
                        descriptions = await image_desc_service.generate_descriptions(
                            photos=photos,
                            markdown_content=markdown,
                            filenames=filenames,
                        )

                        for i, desc in enumerate(descriptions):
                            if i >= len(image_ids):
                                break
                            image_id = image_ids[i]
                            img_record = (
                                session.query(BatchJobImage)
                                .filter_by(id=image_id)
                                .first()
                            )
                            if img_record:
                                img_record.alt = desc.get("alt", "")
                                img_record.title = desc.get("title", "")
                                img_record.description = desc.get("caption", "")
                                descriptions_generated += 1

                        session.commit()
                        logger.info(f"✅ Описания для модели {model} сохранены")

                    except Exception as e:
                        logger.error(f"Ошибка генерации описаний для {model}: {e}")
                        continue

            if descriptions_generated > 0:
                await callback.message.answer(
                    f"🏷️ Сгенерировано {descriptions_generated} описаний"
                )

            gateway_client = GatewayClient()

            with session_maker() as session:
                images = (
                    session.query(BatchJobImage)
                    .filter(BatchJobImage.status == "SUCCEEDED")
                    .filter(BatchJobImage.result_file.isnot(None))
                    .filter(BatchJobImage.title.isnot(None))
                    .filter(BatchJobImage.description.isnot(None))
                    .filter(BatchJobImage.published.is_(False))
                    .all()
                )

                if not images:
                    await callback.message.answer("ℹ️ Нет изображений для публикации")
                    return

                await callback.message.answer(
                    f"📷 Публикация {len(images)} изображений..."
                )

                published_count = 0
                error_count = 0
                published_urls: list[str] = []

                for img in images:
                    try:
                        if img.image_cms_id:
                            logger.info(
                                f"Изображение {img.id} уже загружено (cms_id={img.image_cms_id}), "
                                "добавляем в галерею..."
                            )
                            image_id = int(img.image_cms_id)
                        else:
                            if not img.result_file:
                                error_count += 1
                                continue
                            photo_bytes = drive_service.download_file(img.result_file)
                            if not photo_bytes:
                                logger.warning(
                                    f"Не удалось скачать файл {img.result_file}"
                                )
                                error_count += 1
                                continue

                            upload_result = await gateway_client.upload_image(
                                image_data=photo_bytes,
                                filename=img.get_cms_filename(),
                                title=img.title or "Изображение без названия",
                                description=img.alt,
                                caption=img.description,
                                collection_path=img.get_collection_path(),
                            )

                            image_id = upload_result.image_id
                            img.image_cms_id = str(image_id)
                            session.commit()
                            logger.info(f"✓ Изображение загружено: cms_id={image_id}")

                        if not img.page_url:
                            logger.warning(f"Нет page_url для изображения {img.id}")
                            continue

                        gallery_result = await gateway_client.add_gallery_image(
                            page_url=img.page_url,
                            image_id=image_id,
                        )

                        if gallery_result.success:
                            img.published = True
                            session.commit()
                            published_count += 1
                            logger.info(
                                f"✅ Изображение {img.id} опубликовано в галерее {gallery_result.data.model}"
                            )

                            if img.result_file:
                                drive_service.delete_file(img.result_file)

                            if img.source_url:
                                published_urls.append(img.source_url)

                    except Exception as e:
                        logger.error(f"Ошибка публикации изображения {img.id}: {e}")
                        error_count += 1
                        continue

            if published_urls:
                try:
                    sheets_service = GoogleSheetsService(
                        credentials_path=settings.google.credentials_path,
                    )
                    marked_count = sheets_service.mark_images_as_done(published_urls)
                    logger.info(f"Отмечено в таблице: {marked_count} изображений")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении Google Sheets: {e}")

            await callback.message.answer(
                f"✅ *Публикация завершена*\n\n"
                f"├ Опубликовано: {published_count}\n"
                f"└ Ошибок: {error_count}",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.exception("Image publishing failed")
            await callback.message.answer(f"❌ Ошибка публикации: {e}")


_ACTIONS = {
    "parse": _handle_parse,
    "generate": _handle_generate,
    "status": _handle_status,
    "publish": _handle_publish,
}


@router.callback_query(F.data.startswith("action:"))
async def handle_inline_action(callback: CallbackQuery) -> None:
    action = callback.data.split(":", 1)[1]  # type: ignore
    handler = _ACTIONS.get(action)
    if handler is None:
        await callback.answer("❓ Неизвестное действие", show_alert=True)
        return

    await callback.answer()
    await handler(callback)
