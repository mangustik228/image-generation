"""
Сервис для синхронизации файлов Google Drive с gateway.
Проходит по файлам, извлекает уникальные model_name, получает page_url из БД и отправляет в gateway.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from models.models import BatchJobImage, get_session_maker


def extract_product_markdown(data: dict[str, Any]) -> str:
    """
    Извлекает данные из tabs и возвращает текст в виде markdown.

    Args:
        data: JSON ответ от gateway

    Returns:
        Markdown строка с характеристиками и описанием
    """
    lines: list[str] = []

    content = data.get("content", {})
    tabs = content.get("tabs", {})

    # Характеристики
    characteristics = tabs.get("characteristics", [])
    if characteristics:
        lines.append("## Характеристики")
        for section in characteristics:
            title = section.get("title", "")
            if title:
                lines.append(f"### {title}")

            for char in section.get("characteristics", []):
                label = char.get("label", "")
                value = char.get("value", "")
                if label and value:
                    lines.append(f"- **{label}**: {value}")

            lines.append("")  # Пустая строка между секциями

    # Описание (только description из tabs, игнорируем другие)
    description = tabs.get("description", "")
    if description:
        lines.append("## Описание")
        lines.append(description)
        lines.append("")

    # Используемые изображения из gallery_images
    gallery_images = content.get("gallery_images", [])
    if gallery_images:
        lines.append("## Используемые изображения")
        for i, img in enumerate(gallery_images, 1):
            alt = img.get("alt", "")
            title = img.get("title", "")
            if alt or title:
                lines.append(f"### Изображение {i}")
                if title:
                    lines.append(f"- **title**: {title}")
                if alt:
                    lines.append(f"- **alt**: {alt}")
                lines.append("")

    return "\n".join(lines)


@dataclass
class SyncResult:
    """Результат синхронизации."""

    total_files: int = 0
    unique_models: int = 0
    requests_sent: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    deleted_files: int = 0
    errors: list[str] = field(default_factory=list)
    processed_models: list[str] = field(default_factory=list)
    responses: list[dict[str, Any]] = field(default_factory=list)


class SyncService:
    """Сервис для синхронизации файлов Google Drive с gateway."""

    def __init__(self, database_url: str, gateway_url: str):
        """
        Инициализация сервиса.

        Args:
            database_url: URL базы данных
            gateway_url: Базовый URL gateway
        """
        self.database_url = database_url
        self.gateway_url = gateway_url.rstrip("/")
        self._session_maker = get_session_maker(database_url)

    def _get_session(self) -> Session:
        return self._session_maker()

    def _extract_model_name_from_filename(self, filename: str) -> str | None:
        """
        Извлекает model_name из имени файла.
        Формат файла: {slug(model_name)}_{order_number}_{position}_{uuid}.jpg

        Args:
            filename: Имя файла

        Returns:
            model_name (slug) или None если не удалось извлечь
        """
        # Убираем расширение
        name_without_ext = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Паттерн: slug_ordernumber_position_uuid
        # slug может содержать дефисы, order_number и position - числа/строки, uuid - 8 символов
        parts = name_without_ext.rsplit("_", 3)

        if len(parts) >= 4:
            # Первая часть - это slug (model_name)
            return parts[0]

        return None

    def _get_unique_model_names_from_files(
        self, files: list[dict]
    ) -> dict[str, list[str]]:
        """
        Извлекает уникальные model_name из списка файлов.

        Args:
            files: Список файлов из Google Drive

        Returns:
            Словарь {model_name_slug: [file_ids]}
        """
        model_files: dict[str, list[str]] = {}

        for file_info in files:
            filename = file_info.get("name", "")
            file_id = file_info.get("id", "")

            model_slug = self._extract_model_name_from_filename(filename)
            if model_slug:
                if model_slug not in model_files:
                    model_files[model_slug] = []
                model_files[model_slug].append(file_id)

        return model_files

    def _get_page_urls_for_model(self, model_name_slug: str) -> list[str]:
        """
        Получает page_url из БД для заданного model_name (slug).

        Args:
            model_name_slug: Slug модели (из имени файла)

        Returns:
            Список уникальных page_url
        """
        with self._get_session() as session:
            # Ищем записи где model_name содержит этот slug
            # Используем LIKE для поиска по slug
            images = (
                session.query(BatchJobImage)
                .filter(BatchJobImage.status == "SUCCEEDED")
                .filter(BatchJobImage.page_url.isnot(None))
                .filter(BatchJobImage.page_url != "")
                .all()
            )

            page_urls = set()
            for img in images:
                # Проверяем соответствие slug
                from slugify import slugify

                img_slug = slugify(img.model_name, lowercase=True)
                if img_slug == model_name_slug:
                    page_urls.add(img.page_url)

            return list(page_urls)

    async def _send_to_gateway(self, page_url: str) -> dict[str, Any] | None:
        """
        Отправляет запрос в gateway.

        Args:
            page_url: URL страницы для отправки

        Returns:
            JSON ответ от gateway или None при ошибке
        """
        full_url = f"{self.gateway_url}{page_url}"
        logger.info(f"Отправляю запрос в gateway: {full_url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(full_url)
                response.raise_for_status()
                logger.info(f"Gateway ответил: {response.status_code}")
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Gateway вернул ошибку {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при запросе в gateway: {e}")
            return None

    async def sync_files(self, drive_service, check_deleted: bool = True) -> SyncResult:
        """
        Основной метод синхронизации.
        Проходит по файлам Google Drive, извлекает уникальные model_name,
        получает page_url из БД и отправляет запросы в gateway.

        Args:
            drive_service: GoogleDriveService
            check_deleted: Проверять ли удалённые файлы

        Returns:
            SyncResult со статистикой
        """
        result = SyncResult()

        # 1. Получаем список файлов из Google Drive
        logger.info("Получаю список файлов из Google Drive...")
        files = drive_service.list_files()
        result.total_files = len(files)

        if not files:
            logger.warning("Файлы не найдены в Google Drive")
            # Всё равно проверяем удалённые файлы в БД
            if check_deleted:
                deleted_count = await self._check_deleted_files(drive_service)
                result.deleted_files = deleted_count
            return result

        # 2. Извлекаем уникальные model_name
        model_files = self._get_unique_model_names_from_files(files)
        result.unique_models = len(model_files)
        logger.info(f"Найдено {result.unique_models} уникальных моделей")

        # 3. Для каждой модели получаем page_url и отправляем в gateway
        sent_urls: set[str] = set()

        for model_slug, file_ids in model_files.items():
            logger.info(f"Обрабатываю модель: {model_slug} ({len(file_ids)} файлов)")
            result.processed_models.append(model_slug)

            page_urls = self._get_page_urls_for_model(model_slug)

            if not page_urls:
                logger.warning(f"Не найден page_url для модели {model_slug}")
                continue

            for page_url in page_urls:
                # Избегаем дублирования запросов
                if page_url in sent_urls:
                    continue

                sent_urls.add(page_url)
                result.requests_sent += 1

                response_data = await self._send_to_gateway(page_url)
                if response_data:
                    result.requests_success += 1
                    result.responses.append(response_data)
                else:
                    result.requests_failed += 1
                    result.errors.append(f"Ошибка для {page_url}")

        # 4. Опционально: проверяем удалённые файлы в БД
        if check_deleted:
            deleted_count = await self._check_deleted_files(drive_service)
            result.deleted_files = deleted_count

        logger.info(
            f"Синхронизация завершена: {result.requests_success}/{result.requests_sent} успешных запросов"
        )

        return result

    async def _check_deleted_files(self, drive_service) -> int:
        """
        Проверяет файлы в БД на предмет удаления из Google Drive.
        Проверяются только неопубликованные изображения со статусом SUCCEEDED.
        При обнаружении удалённого файла статус меняется на DELETED.

        Args:
            drive_service: GoogleDriveService

        Returns:
            Количество удалённых файлов
        """
        deleted_count = 0

        with self._get_session() as session:
            images = (
                session.query(BatchJobImage)
                .filter(BatchJobImage.status == "SUCCEEDED")
                .filter(BatchJobImage.result_file.isnot(None))
                .filter(BatchJobImage.published == False)
                .all()
            )

            for img in images:
                if img.result_file and not drive_service.check_file_exists(
                    img.result_file
                ):
                    logger.warning(
                        f"Файл удалён из Google Drive: {img.result_file} (модель: {img.model_name})"
                    )
                    img.status = "DELETED"
                    deleted_count += 1

            session.commit()

        return deleted_count
