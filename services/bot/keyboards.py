from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Обновить изображения")],
            [KeyboardButton(text="🎨 Отправить на генерацию")],
            [KeyboardButton(text="📊 Проверить задания")],
            [KeyboardButton(text="📤 Загрузить фотографии")],
        ],
        resize_keyboard=True,
    )
