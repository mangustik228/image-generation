import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from services.batch.batch_service import BatchService

router = Router()

PAGE_SIZE = 5


def _get_batch_service() -> BatchService:
    from config import settings

    return BatchService(
        api_key=settings.gemini.api_key, database_url=settings.database.url
    )


class ChangePromptState(StatesGroup):
    waiting_for_text = State()


@router.message(F.text == "📝 Показать базовый промпт")
async def handle_show_prompt(message: Message) -> None:
    service = _get_batch_service()
    prompt = service.get_active_prompt()
    text = prompt if prompt else "_(промпт не задан)_"
    await message.answer(f"📝 *Базовый промпт:*\n\n{text}", parse_mode="Markdown")


@router.message(F.text == "✏️ Поменять базовый промпт")
async def handle_change_prompt_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ChangePromptState.waiting_for_text)
    await message.answer("Введите новый базовый промпт:", parse_mode="Markdown")


@router.message(ChangePromptState.waiting_for_text)
async def handle_change_prompt_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("Промпт не может быть пустым.")
        return
    service = _get_batch_service()
    service.set_active_prompt(new_text)
    await message.answer(
        f"✅ Базовый промпт обновлён:\n\n{new_text}", parse_mode="Markdown"
    )


@router.message(F.text == "📋 Предыдущие промпты")
async def handle_prompt_history(message: Message) -> None:
    await _send_prompt_history_page(message, page=1)


@router.callback_query(F.data.startswith("prompts_page:"))
async def handle_prompt_history_page(callback: CallbackQuery) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    page = int(callback.data.split(":")[1])
    await _send_prompt_history_page(callback.message, page=page, edit=True)
    await callback.answer()


async def _send_prompt_history_page(
    message: Message, page: int, edit: bool = False
) -> None:
    service = _get_batch_service()
    prompts, total = service.get_recent_prompts(page=page, page_size=PAGE_SIZE)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    if not prompts:
        text = "История промптов пуста."
    else:
        lines = [f"📋 *История промптов* (стр. {page}/{total_pages}):\n"]
        for i, p in enumerate(prompts, start=(page - 1) * PAGE_SIZE + 1):
            active_mark = " ✅" if p.is_active else ""
            date_str = p.created_at.strftime("%d.%m.%Y %H:%M")
            lines.append(f"*{i}.* [{date_str}]{active_mark}\n{p.text}\n")
        text = "\n".join(lines)

    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад", callback_data=f"prompts_page:{page - 1}"
            )
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперёд ➡️", callback_data=f"prompts_page:{page + 1}"
            )
        )

    markup = (
        InlineKeyboardMarkup(inline_keyboard=[nav_buttons]) if nav_buttons else None
    )

    if edit:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=markup)
