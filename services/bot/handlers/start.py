from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from services.bot.keyboards import get_main_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None  # type: ignore
    if user_id is None or user_id not in settings.telegram.authorized_users:
        await message.answer("⛔ Доступ запрещён")
        return
    await message.answer(
        "Привет! Используй кнопку ниже.", reply_markup=get_main_keyboard()
    )
