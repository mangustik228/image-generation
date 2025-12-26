import asyncio

from loguru import logger

from services.bot import run_bot


async def main():
    logger.info("Starting Telegram bot...")
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
