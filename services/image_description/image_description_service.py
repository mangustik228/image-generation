"""
Сервис для генерации описаний изображений (alt/title/caption) через Gemini API.
"""

import io
import json
import re
from typing import Any

from google import genai
from google.genai import types
from loguru import logger
from PIL import Image

from config import settings

IMAGE_DESCRIPTION_PROMPT = """
Создай SEO-оптимизированные описания для изображений мебельного изделия.

ДАННЫЕ О ТОВАРЕ (markdown):
{markdown_content}

Всего изображений: {images_count}

ТРЕБОВАНИЯ К SEO-ОПИСАНИЯМ ИЗОБРАЖЕНИЙ:

1. **TITLE** (заголовок изображения, 25-40 символов):
   - Структура: [Тип изделия] [Модель] - [Ракурс/Особенность]
   - Примеры: "Стол переговорный Лидер - общий вид", "Ювелирная витрина ЮВ-300 - боковой вид"

2. **ALT** (alt-текст, 60-100 символов):
   - Структура: [Тип изделия] [Модель] [Материал/цвет] [Особенность]
   - Опиши именно то, что видно на изображении
   - Примеры: "Переговорный стол Лидер из ЛДСП венге на 12 человек."

3. **CAPTION** (подробное описание, 120-200 символов):
   - Что конкретно показано (деталь, ракурс, функция)
   - Материалы и особенности
   - Польза для пользователя

ПРИНЦИПЫ:
- Каждое описание уникально
- Соответствует тому, что видно на фото
- Читается естественно

ФОРМАТ ОТВЕТА (строго JSON, без markdown-разметки):
{{
    "images": [
        {{
            "title": "заголовок",
            "alt": "alt-текст",
            "caption": "подробное описание"
        }}
    ]
}}

Количество объектов в массиве images должно соответствовать количеству изображений ({images_count}).

ВАЖНО: Верни ТОЛЬКО JSON-объект. Без markdown-разметки, без дополнительного текста.
"""


class ImageDescriptionService:
    """Сервис для генерации описаний изображений через Gemini API."""

    def __init__(self):
        """Инициализация Gemini клиента."""
        self.client = genai.Client(api_key=settings.gemini.api_key)
        self.model = settings.gemini.description_model
        logger.info(f"ImageDescriptionService инициализирован с моделью: {self.model}")

    async def generate_descriptions(
        self,
        photos: list[bytes],
        markdown_content: str,
        filenames: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """
        Генерация описаний для изображений товара.

        Args:
            photos: Список байтов изображений
            markdown_content: Markdown с характеристиками и описанием товара
            filenames: Список имён файлов для логирования

        Returns:
            list: Список словарей с title, alt, caption для каждого изображения
        """
        if not photos:
            return []

        try:
            logger.info(
                f"Генерация описаний для {len(photos)} изображений через Gemini API..."
            )

            # Подготавливаем изображения
            contents: list[types.Part] = []

            for i, photo_bytes in enumerate(photos):
                filename = (
                    filenames[i] if filenames and i < len(filenames) else f"image_{i}"
                )
                resized_photo = self._resize_image_for_api(
                    photo_bytes, filename=filename
                )
                contents.append(
                    types.Part.from_bytes(
                        data=resized_photo,
                        mime_type="image/jpeg",
                    )
                )

            # Добавляем текстовый промпт
            prompt = IMAGE_DESCRIPTION_PROMPT.format(
                markdown_content=markdown_content,
                images_count=len(photos),
            )
            contents.append(types.Part.from_text(text=prompt))

            # Отправляем запрос
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,  # type: ignore[arg-type]
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                ),
            )

            logger.info("Получен ответ от Gemini API")

            response_text = response.text or ""
            result = self._parse_response(response_text)

            images = result.get("images", [])
            logger.info(f"Описания успешно сгенерированы: {len(images)} шт.")
            return images

        except Exception as e:
            logger.error(f"Ошибка при генерации описаний изображений: {e}")
            raise

    def _resize_image_for_api(
        self,
        image_bytes: bytes,
        max_size: int = 1024,
        max_bytes: int = 800_000,
        filename: str = "unknown",
    ) -> bytes:
        """
        Уменьшает изображение для отправки в API с гарантией размера < 800KB.

        Args:
            image_bytes: Исходные байты изображения
            max_size: Максимальный размер по большей стороне
            max_bytes: Максимальный размер в байтах
            filename: Имя файла для логирования

        Returns:
            bytes: Байты уменьшенного изображения
        """
        try:
            original_size = len(image_bytes)
            logger.debug(f"[{filename}] Исходный размер: {original_size / 1024:.2f} KB")

            image = Image.open(io.BytesIO(image_bytes))

            # Конвертируем в RGB если нужно
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            original_width, original_height = image.size

            # Уменьшаем размер если превышает max_size
            width, height = original_width, original_height
            if width > max_size or height > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                width, height = new_width, new_height

            # Пробуем разные уровни качества
            result_bytes: bytes = b""
            for quality in [85, 70, 55, 40, 30]:
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                result_bytes = output.getvalue()

                if len(result_bytes) <= max_bytes:
                    logger.debug(
                        f"[{filename}] Сжато: {original_width}x{original_height} -> {width}x{height}, "
                        f"{original_size / 1024:.2f}KB -> {len(result_bytes) / 1024:.2f}KB (quality={quality})"
                    )
                    return result_bytes

            # Если всё ещё слишком большое - уменьшаем размер ещё сильнее
            for scale in [0.75, 0.5, 0.35, 0.25]:
                new_width = int(width * scale)
                new_height = int(height * scale)
                scaled_image = image.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )

                output = io.BytesIO()
                scaled_image.save(output, format="JPEG", quality=40, optimize=True)
                result_bytes = output.getvalue()

                if len(result_bytes) <= max_bytes:
                    logger.debug(
                        f"Изображение сильно сжато: {original_width}x{original_height} -> {new_width}x{new_height}"
                    )
                    return result_bytes

            logger.warning(
                f"Не удалось сжать изображение до {max_bytes} байт, "
                f"итоговый размер: {len(result_bytes) / 1024:.2f}KB"
            )
            return result_bytes

        except Exception as e:
            logger.error(f"Ошибка при сжатии изображения: {e}")
            raise

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """
        Парсинг ответа от API в структурированный словарь.

        Args:
            response_text: Текст ответа от Gemini API

        Returns:
            dict: Распарсенные данные
        """
        try:
            # Убираем markdown-разметку ```json ... ```
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```"):
                # Убираем первую строку с ```json или ```
                lines = cleaned_text.split("\n")
                # Убираем первую и последнюю строки с ```
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_text = "\n".join(lines)

            # Ищем JSON в ответе
            start_idx = cleaned_text.find("{")
            end_idx = cleaned_text.rfind("}")

            if start_idx == -1 or end_idx == -1:
                logger.warning("JSON не найден в ответе")
                logger.debug(f"Ответ: {response_text[:500]}...")
                return {
                    "raw_response": response_text,
                    "parsing_error": "JSON structure not found in response",
                }

            json_str = cleaned_text[start_idx : end_idx + 1]

            # Пробуем распарсить как есть
            try:
                result = json.loads(json_str)
                logger.debug("JSON успешно распарсен")
                return result
            except json.JSONDecodeError:
                pass

            # Пробуем исправить типичные проблемы
            # 1. Заменяем неэкранированные переносы строк внутри строк
            # 2. Убираем trailing commas
            fixed_json = re.sub(r",\s*([}\]])", r"\1", json_str)

            try:
                result = json.loads(fixed_json)
                logger.debug("JSON успешно распарсен после исправления")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON: {e}")
                logger.debug(f"JSON строка: {json_str[:1000]}...")
                return {
                    "raw_response": response_text,
                    "parsing_error": f"JSON decode error: {e}",
                }

        except Exception as e:
            logger.error(f"Неожиданная ошибка при парсинге ответа: {e}")
            return {
                "raw_response": response_text,
                "parsing_error": f"Unexpected error: {e}",
            }
