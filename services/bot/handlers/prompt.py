from aiogram import F, Router
from aiogram.types import Message

from config import settings
from services.batch.batch_service import BASE_PROMPT

router = Router()


@router.message(F.text == "📝 Показать базовый промпт")
async def handle_show_prompt(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore
    if user_id not in settings.telegram.authorized_users:
        await message.answer("⛔ Доступ запрещён")
        return

    await message.answer(f"📝 *Базовый промпт:*\n\n{BASE_PROMPT}", parse_mode="Markdown")
