from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

HELP_TEXT = (
    "*Доступные команды и кнопки:*\n\n"
    "*Команды:*\n"
    "/start — запустить бота и показать меню\n"
    "/help — показать это сообщение\n\n"
    "*Кнопки меню:*\n"
    "🔄 *Обновить изображения* — запустить парсинг и записать результаты в Google Sheets\n"
    "🎨 *Отправить на генерацию* — скачать изображения из таблицы и создать batch job в Gemini\n"
    "📊 *Проверить задания* — проверить статусы batch jobs и скачать готовые результаты\n"
    "📤 *Загрузить фотографии* — синхронизировать с Gateway, сгенерировать описания и опубликовать изображения\n"
    "📝 *Показать базовый промпт* — вывести базовый промпт для генерации изображений\n"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="Markdown")
