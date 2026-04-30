from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Обновить изображения")],
            [KeyboardButton(text="🎨 Отправить на генерацию")],
            [KeyboardButton(text="📊 Проверить задания")],
            [KeyboardButton(text="📤 Загрузить фотографии")],
            [KeyboardButton(text="📝 Показать базовый промпт")],
        ],
        resize_keyboard=True,
    )


def get_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить изображения", callback_data="action:parse"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Отправить на генерацию", callback_data="action:generate"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Проверить задания", callback_data="action:status"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Загрузить фотографии", callback_data="action:publish"
                )
            ],
        ]
    )
