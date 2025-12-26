import asyncio

parsing_lock = asyncio.Lock()
generation_lock = asyncio.Lock()
status_check_lock = asyncio.Lock()
publish_lock = asyncio.Lock()
