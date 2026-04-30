from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.bot.keyboards import get_main_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Используй кнопку ниже.", reply_markup=get_main_keyboard()
    )
