"""
Gateway API клиент для загрузки изображений и добавления в галерею.
"""

from typing import Optional

import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class ImageUploadResponse(BaseModel):
    image_id: int
    title: str
    description: Optional[str] = None
    caption: Optional[str] = None
    image_url: str
    collection_path: str


class GalleryAddImageData(BaseModel):
    model: str
    image_id: int
    gallery_count: int


class GalleryAddImageResponse(BaseModel):
    success: bool
    message: str
    data: GalleryAddImageData


class GatewayClient:
    """Клиент для работы с Gateway API."""

    def __init__(self, base_url: Optional[str] = None):
        """
        Инициализация клиента.

        Args:
            base_url: Базовый URL Gateway API. По умолчанию берётся из settings.
        """
        self.base_url = (base_url or settings.gateway.url).rstrip("/")
        self.headers = {"x-api-key": settings.external_api_key}
        logger.info(f"GatewayClient инициализирован: {self.base_url}")

    async def upload_image(
        self,
        image_data: bytes,
        filename: str,
        title: str,
        description: Optional[str] = None,
        caption: Optional[str] = None,
        collection_path: Optional[str] = None,
    ) -> ImageUploadResponse:
        """
        Загрузка изображения в CMS через Gateway.

        Args:
            image_data: Байты изображения
            filename: Имя файла
            title: Заголовок изображения
            description: Описание (опционально)
            caption: Подпись (опционально)
            collection_path: Путь коллекции (опционально)

        Returns:
            ImageUploadResponse с image_id и другими данными
        """
        url = f"{self.base_url}/images/upload"

        files = {"file": (filename, image_data, "image/jpeg")}
        data = {"title": title}

        if description:
            data["description"] = description
        if caption:
            data["caption"] = caption
        if collection_path:
            data["collection_path"] = collection_path

        logger.info(f"Загрузка изображения: {filename}, title={title}")

        async with httpx.AsyncClient(timeout=60.0, headers=self.headers) as client:
            response = await client.post(url, files=files, data=data)
            response.raise_for_status()

            result = ImageUploadResponse(**response.json())
            logger.info(f"Изображение загружено: image_id={result.image_id}")
            return result

    async def add_gallery_image(
        self,
        page_url: str,
        image_id: int,
    ) -> GalleryAddImageResponse:
        """
        Добавление изображения в галерею товара.

        Args:
            page_url: URL страницы товара (category/subcategory/model)
            image_id: ID изображения в CMS

        Returns:
            GalleryAddImageResponse с результатом операции
        """
        # page_url уже содержит /products/category/subcategory/model
        # Нужно добавить /gallery/add
        url = f"{self.base_url}{page_url}/gallery/add"

        logger.info(f"Добавление изображения в галерею: {url}, image_id={image_id}")

        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            response = await client.post(url, json={"image_id": image_id})
            response.raise_for_status()

            result = GalleryAddImageResponse(**response.json())
            logger.info(
                f"Изображение добавлено в галерею: {result.data.model}, "
                f"gallery_count={result.data.gallery_count}"
            )
            return result

    async def upload_and_add_to_gallery(
        self,
        image_data: bytes,
        filename: str,
        title: str,
        page_url: str,
        description: Optional[str] = None,
        caption: Optional[str] = None,
        collection_path: Optional[str] = None,
    ) -> tuple[ImageUploadResponse, GalleryAddImageResponse]:
        """
        Загрузка изображения и добавление в галерею товара.

        Args:
            image_data: Байты изображения
            filename: Имя файла
            title: Заголовок изображения
            page_url: URL страницы товара
            description: Описание (опционально)
            caption: Подпись (опционально)
            collection_path: Путь коллекции (опционально)

        Returns:
            Tuple из ImageUploadResponse и GalleryAddImageResponse
        """
        # 1. Загружаем изображение
        upload_result = await self.upload_image(
            image_data=image_data,
            filename=filename,
            title=title,
            description=description,
            caption=caption,
            collection_path=collection_path,
        )

        # 2. Добавляем в галерею
        gallery_result = await self.add_gallery_image(
            page_url=page_url,
            image_id=upload_result.image_id,
        )

        return upload_result, gallery_result
