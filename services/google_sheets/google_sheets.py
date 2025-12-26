from collections import Counter
from dataclasses import dataclass

import gspread
from gspread.utils import ValueInputOption
from loguru import logger

from services.parser.schemas import ParseResult


@dataclass
class ImageRecord:
    """Record from 'изображения' sheet."""

    model: str
    order_number: str
    category: str
    status: str
    position: str
    custom_prompt: str
    attempt_number: str
    url: str
    page_url: str


class GoogleSheetsService:
    SPREADSHEET_NAME = "По заказам"
    MIGRATION_SHEET = "миграция"
    IMAGES_SHEET = "изображения"

    def __init__(self, credentials_path: str):
        self.gc = gspread.service_account(filename=credentials_path)
        self.spreadsheet = self.gc.open(self.SPREADSHEET_NAME)
        logger.info(f"Connected to spreadsheet: {self.SPREADSHEET_NAME}")

    def get_order_numbers_map(self) -> dict[str, str]:
        """
        Read 'миграция' sheet and build a map of model -> order_number.
        If a model appears more than once, its order_number is set to empty string.
        Column A = model, Column B = order_number (Заказ)
        """
        worksheet = self.spreadsheet.worksheet(self.MIGRATION_SHEET)
        all_values = worksheet.get_all_values()

        model_counts: Counter[str] = Counter()
        model_to_order: dict[str, str] = {}

        for row in all_values[1:]:
            if len(row) < 2:
                continue
            model = row[0].strip()
            order_number = row[1].strip()
            if not model:
                continue
            model_counts[model] += 1
            model_to_order[model] = order_number

        result: dict[str, str] = {}
        for model, order_number in model_to_order.items():
            if model_counts[model] > 1:
                result[model] = ""
            else:
                result[model] = order_number

        logger.info(f"Loaded {len(result)} models from '{self.MIGRATION_SHEET}' sheet")
        return result

    def populate_order_numbers(self, items: list[ParseResult]) -> list[ParseResult]:
        """
        Populate order_number field in ParseResult items based on 'миграция' sheet.
        """
        order_map = self.get_order_numbers_map()

        for item in items:
            item.order_number = order_map.get(item.model, "")

        populated_count = sum(1 for item in items if item.order_number)
        logger.info(f"Populated order_number for {populated_count}/{len(items)} items")
        return items

    def get_existing_urls(self) -> set[str]:
        """
        Get all existing image URLs from 'изображения' sheet (column H).
        """
        worksheet = self.spreadsheet.worksheet(self.IMAGES_SHEET)
        all_values = worksheet.get_all_values()

        urls: set[str] = set()
        for row in all_values[1:]:
            if len(row) >= 8:
                url = row[7].strip()
                if url:
                    urls.add(url)

        logger.info(f"Found {len(urls)} existing URLs in '{self.IMAGES_SHEET}' sheet")
        return urls

    def write_results(self, items: list[ParseResult]) -> int:
        """
        Write ParseResult items to 'изображения' sheet.
        Columns: A(model), B(order_number), C(category), D(status='Новое'),
                 E(position), H(image_url)

        Returns the number of new items added.
        """
        existing_urls = self.get_existing_urls()
        worksheet = self.spreadsheet.worksheet(self.IMAGES_SHEET)

        new_items = [item for item in items if item.image_url not in existing_urls]

        if not new_items:
            logger.info("No new items to add")
            return 0

        rows_to_add: list[list[str]] = []
        for item in new_items:
            row = [
                item.model,
                item.order_number,
                item.category,
                "Новое",
                str(item.position),
                "",
                0,
                item.image_url,
                item.page_url,
            ]
            rows_to_add.append(row)

        worksheet.append_rows(
            rows_to_add, value_input_option=ValueInputOption.user_entered
        )
        logger.info(
            f"Added {len(rows_to_add)} new items to '{self.IMAGES_SHEET}' sheet"
        )
        return len(rows_to_add)

    def get_pending_images(self) -> list[ImageRecord]:
        """
        Get all records from 'изображения' sheet where:
        - Status != 'Готово' and Status != 'И так классно'
        - Column F (Кастомный промпт) is filled

        Columns: A(Модель), B(Заказ), C(Категория), D(Статус),
                 E(Порядковый номер), F(Кастомный промпт), G(№ попытки), H(url), I(page_url)
        """
        worksheet = self.spreadsheet.worksheet(self.IMAGES_SHEET)
        all_values = worksheet.get_all_values()

        excluded_statuses = {"Готово", "И так классно"}
        records: list[ImageRecord] = []

        for row in all_values[1:]:
            if len(row) < 8:
                continue

            status = row[3].strip()
            custom_prompt = row[5].strip()

            if status in excluded_statuses:
                continue
            if not custom_prompt:
                continue

            record = ImageRecord(
                model=row[0].strip(),
                order_number=row[1].strip(),
                category=row[2].strip(),
                status=status,
                position=row[4].strip(),
                custom_prompt=custom_prompt,
                attempt_number=row[6].strip() if len(row) > 6 else "",
                url=row[7].strip() if len(row) > 7 else "",
                page_url=row[8].strip() if len(row) > 8 else "",
            )
            records.append(record)

        logger.info(
            f"Found {len(records)} pending images with custom prompts in '{self.IMAGES_SHEET}' sheet"
        )
        return records

    def mark_image_as_done(self, image_url: str) -> bool:
        """
        Mark image as 'Готово' in 'изображения' sheet by its URL.

        Args:
            image_url: URL of the image (column H)

        Returns:
            True if image was found and marked, False otherwise
        """
        worksheet = self.spreadsheet.worksheet(self.IMAGES_SHEET)
        all_values = worksheet.get_all_values()

        for row_idx, row in enumerate(all_values[1:], start=2):
            if len(row) >= 8:
                url = row[7].strip()
                if url == image_url:
                    worksheet.update_cell(row_idx, 4, "Готово")
                    logger.info(f"Marked image as 'Готово': {image_url}")
                    return True

        logger.warning(f"Image not found in sheet: {image_url}")
        return False

    def mark_images_as_done(self, image_urls: list[str]) -> int:
        """
        Mark multiple images as 'Готово' in 'изображения' sheet.

        Args:
            image_urls: List of image URLs to mark

        Returns:
            Number of images successfully marked
        """
        if not image_urls:
            return 0

        worksheet = self.spreadsheet.worksheet(self.IMAGES_SHEET)
        all_values = worksheet.get_all_values()

        urls_set = set(image_urls)
        marked_count = 0

        for row_idx, row in enumerate(all_values[1:], start=2):
            if len(row) >= 8:
                url = row[7].strip()
                if url in urls_set:
                    worksheet.update_cell(row_idx, 4, "Готово")
                    marked_count += 1
                    logger.debug(f"Marked image as 'Готово': {url}")

        logger.info(f"Marked {marked_count}/{len(image_urls)} images as 'Готово'")
        return marked_count
