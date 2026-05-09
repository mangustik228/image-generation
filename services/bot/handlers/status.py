import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from loguru import logger

from config import settings
from services.batch import BatchService
from services.bot.formatters import format_status_result
from services.bot.locks import status_check_lock
from services.google_drive import GoogleDriveService
from services.google_drive.auth_flow import (
    cancel_auth_flow,
    complete_auth_flow,
    start_auth_flow,
)

router = Router()


class GoogleAuthState(StatesGroup):
    waiting_for_code = State()


def _is_invalid_grant_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "invalid_grant" in msg or "token has been expired" in msg


async def _start_reauth(
    message: Message, state: FSMContext, error: BaseException
) -> None:
    logger.warning(f"Google token invalid, starting re-auth flow: {error}")
    try:
        auth_url = start_auth_flow()
    except Exception as ex:
        await message.answer(f"❌ Не удалось запустить авторизацию: {ex}")
        return

    await state.set_state(GoogleAuthState.waiting_for_code)
    await message.answer(
        "⚠️ Токен Google Drive истёк или отозван. Нужна повторная авторизация.\n\n"
        "1) Откройте ссылку и подтвердите доступ:\n"
        f"{auth_url}\n\n"
        "2) После согласия браузер перенаправит вас на адрес вида "
        "`http://localhost/?code=...` (страница не откроется — это нормально).\n\n"
        "3) Скопируйте *весь URL из адресной строки* и пришлите его сюда "
        "(или только значение параметра `code`).\n\n"
        "Для отмены отправьте /cancel_auth.",
        disable_web_page_preview=True,
        parse_mode="Markdown",
    )


@router.message(F.text == "📊 Проверить задания")
async def handle_check_status(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id  # type: ignore
    if status_check_lock.locked():
        await message.answer("⏳ Проверка статусов уже запущена. Подождите завершения.")
        return

    async with status_check_lock:
        logger.info(f"User {user_id} started status check")

        try:
            await message.answer("🔍 Проверяю статусы batch jobs...")

            batch_service = BatchService(
                api_key=settings.gemini.api_key,
                database_url=settings.database.url,
                model=settings.gemini.model,
            )

            drive_service = GoogleDriveService(
                folder_id=settings.google.drive_folder_id,
            )

            # Проверяем и скачиваем результаты для PENDING и RUNNING jobs
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: batch_service.check_and_download_results(drive_service),
            )

            # Получаем общую статистику и добавляем данные о текущей обработке
            overall_stats = await asyncio.get_event_loop().run_in_executor(
                None,
                batch_service.get_overall_statistics,
            )

            # Переносим статистику текущей обработки в overall_stats
            overall_stats.current_images_succeeded = result.current_images_succeeded
            overall_stats.current_images_failed = result.current_images_failed
            overall_stats.errors_grouped = result.errors_grouped

            await message.answer(
                format_status_result(overall_stats, show_current=True),
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.exception("Status check failed")
            if _is_invalid_grant_error(e):
                await _start_reauth(message, state, e)
            else:
                await message.answer(f"❌ Ошибка проверки статусов: {e}")


@router.message(F.text == "/cancel_auth")
async def handle_cancel_auth(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current == GoogleAuthState.waiting_for_code.state:
        await state.clear()
        cancel_auth_flow()
        await message.answer("Авторизация отменена.")


@router.message(GoogleAuthState.waiting_for_code)
async def handle_auth_code(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пришлите URL или код авторизации.")
        return

    try:
        await asyncio.get_event_loop().run_in_executor(None, complete_auth_flow, text)
    except Exception as e:
        logger.exception("OAuth completion failed")
        await message.answer(
            f"❌ Не удалось завершить авторизацию: {e}\n"
            "Попробуйте снова прислать URL/код или /cancel_auth для отмены."
        )
        return

    await state.clear()
    await message.answer(
        "✅ Авторизация успешна! Нажмите *📊 Проверить задания* ещё раз.",
        parse_mode="Markdown",
    )
