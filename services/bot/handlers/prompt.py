from aiogram import F, Router
from aiogram.types import Message

from services.batch.batch_service import BASE_PROMPT

router = Router()


@router.message(F.text == "📝 Показать базовый промпт")
async def handle_show_prompt(message: Message) -> None:
    await message.answer(
        f"📝 *Базовый промпт:*\n\n{BASE_PROMPT}", parse_mode="Markdown"
    )
