from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import settings


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            if user_id is None or user_id not in settings.telegram.authorized_users:
                await event.answer("⛔ Доступ запрещён")
                return
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            if user_id not in settings.telegram.authorized_users:
                await event.answer("⛔ Доступ запрещён", show_alert=True)
                return

        return await handler(event, data)
