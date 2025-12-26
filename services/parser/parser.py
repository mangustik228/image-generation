import httpx
from loguru import logger

from config import settings

from .schemas import ParseResult, ParseStats


class Parser:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def parse(self, text: str) -> tuple[list[ParseResult], ParseStats]:
        result: list[ParseResult] = []
        stats = ParseStats()

        async with httpx.AsyncClient() as client:
            try:
                catalog_urls = await self.parse_menu(client)
            except Exception as e:
                error_msg = f"Failed to parse menu: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)
                return result, stats

            stats.catalogs_total = len(catalog_urls)
            logger.debug(f"Parsed catalog URLs: {catalog_urls}")

            products_urls: list[str] = []
            for catalog_url in catalog_urls:
                try:
                    products_urls_in_catalog = await self.parse_catalog(
                        client, catalog_url
                    )
                    products_urls.extend(products_urls_in_catalog)
                    stats.catalogs_parsed += 1
                except Exception as e:
                    stats.catalogs_failed += 1
                    error_msg = f"Failed to parse catalog {catalog_url}: {e}"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)

            stats.products_total = len(products_urls)

            for product_url in products_urls:
                try:
                    product_items = await self.parse_product(client, product_url)
                    result.extend(product_items)
                    stats.products_parsed += 1
                    stats.images_total += len(product_items)
                except Exception as e:
                    stats.products_failed += 1
                    error_msg = f"Failed to parse product {product_url}: {e}"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)

        logger.info(
            f"Parsed {stats.images_total} images from "
            f"{stats.products_parsed}/{stats.products_total} products, "
            f"{stats.catalogs_parsed}/{stats.catalogs_total} catalogs"
        )
        if stats.errors:
            logger.warning(f"Encountered {len(stats.errors)} errors during parsing")

        return result, stats

    async def parse_menu(self, client: httpx.AsyncClient) -> list[str]:
        catalogs_urls: list[str] = []
        response = await client.get(f"{self.base_url}/menu")
        response.raise_for_status()

        for category in response.json()[0].get("items"):
            for catalog in category.get("items"):
                catalogs_urls.append(catalog.get("url"))

        return catalogs_urls

    async def parse_catalog(
        self, client: httpx.AsyncClient, catalog_url: str
    ) -> list[str]:
        if catalog_url == "/products/accessories/chairs/":
            logger.info("Skipping chairs catalog")
            return []
        logger.debug(f"Start parse catalog: {catalog_url}")
        products_urls: list[str] = []
        response = await client.get(f"{self.base_url}{catalog_url}")
        response.raise_for_status()
        for item in response.json().get("content").get("catalog"):
            products_urls.append(item.get("url"))

        return products_urls

    async def parse_product(
        self, client: httpx.AsyncClient, product_url: str
    ) -> list[ParseResult]:
        result: list[ParseResult] = []
        response = await client.get(f"{self.base_url}{product_url}")
        response.raise_for_status()
        data = response.json()
        content = data.get("content")
        page_url = data.get("url")
        model = content.get("model", "")
        category = self._extract_category(data)
        for index, image in enumerate(content.get("gallery_images", []), 1):
            item = ParseResult(
                model=model,
                image_url=f"{settings.cdn.url}{image.get('full_jpeg', '')}",
                position=index,
                category=category,
                page_url=page_url,
            )
            result.append(item)
        logger.debug(f"Parsed product, model: {model}, total images: {len(result)}")
        return result

    def _extract_category(self, data: dict) -> str:
        json_ld = data.get("json_ld", {})
        graph = json_ld.get("@graph", [])
        for item in graph:
            if item.get("@type") == "Product":
                return item.get("category", "достал херню")
        return "не найдено"
