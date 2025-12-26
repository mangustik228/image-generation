from pathlib import Path

import httpx
from loguru import logger


async def download_image(url: str, dest_path: Path) -> bool:
    """Скачивает изображение по URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            dest_path.write_bytes(response.content)
            return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False
