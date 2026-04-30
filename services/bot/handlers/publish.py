from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from config import settings
from models.models import BatchJobImage, get_session_maker
from services.bot.locks import publish_lock
from services.gateway import GatewayClient
from services.google_drive import GoogleDriveService
from services.google_sheets import GoogleSheetsService
from services.sync import SyncService

router = Router()


@router.message(F.text == "📤 Загрузить фотографии")
async def handle_publish_images(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore
    if publish_lock.locked():
        await message.answer("⏳ Публикация уже запущена. Подождите завершения.")
        return

    async with publish_lock:
        logger.info(f"User {user_id} started image publishing")

        try:
            await message.answer("📤 Начинаю загрузку фотографий...")

            drive_service = GoogleDriveService(
                folder_id=settings.google.drive_folder_id,
            )
            session_maker = get_session_maker(settings.database.url)

            # ===== ШАГ 1: Синхронизация с Gateway =====
            sync_service = SyncService(
                database_url=settings.database.url,
                gateway_url=settings.gateway.url,
            )

            await message.answer("🔄 Синхронизация с Gateway...")
            result = await sync_service.sync_files(drive_service, check_deleted=True)

            logger.info(
                f"Синхронизация: {result.requests_success} успешных, {result.requests_failed} ошибок"
            )

            # ===== ШАГ 2: Публикация изображений =====
            gateway_client = GatewayClient()

            with session_maker() as session:
                images = (
                    session.query(BatchJobImage)
                    .filter(BatchJobImage.status == "SUCCEEDED")
                    .filter(BatchJobImage.result_file.isnot(None))
                    .filter(BatchJobImage.published.is_(False))
                    .all()
                )

                if not images:
                    await message.answer("ℹ️ Нет изображений для публикации")
                    return

                await message.answer(f"📷 Публикация {len(images)} изображений...")

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
                                title=img.model_name,
                                description=img.model_name,
                                caption=img.model_name,
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

            await message.answer(
                f"✅ *Публикация завершена*\n\n"
                f"├ Опубликовано: {published_count}\n"
                f"└ Ошибок: {error_count}",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.exception("Image publishing failed")
            await message.answer(f"❌ Ошибка публикации: {e}")
