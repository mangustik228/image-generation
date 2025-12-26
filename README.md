# Image Generation Bot

Telegram-бот для автоматизации работы с изображениями товаров: парсинг с сайта, AI-генерация улучшенных версий через Gemini, автоматическое создание SEO-описаний и публикация в CMS.

## 🎯 Назначение

Бот решает задачу массовой обработки изображений товаров:

1. **Парсинг** — скачивание изображений с сайта и занесение в Google Таблицу
2. **Подготовка промптов** — ручное написание промптов для изображений, требующих улучшения
3. **Batch-генерация** — массовая генерация улучшенных изображений через Gemini API
4. **Модерация** — проверка результатов в папке Google Drive (хорошие оставляем, плохие удаляем)
5. **Генерация описаний** — AI-анализ изображений для создания alt/title/caption с учётом контекста товара
6. **Публикация** — загрузка изображений в CMS с присвоенными атрибутами

## 🛠 Технологии

### Основной стек
- **Python 3.13+** — язык программирования
- **uv** — менеджер пакетов и виртуальных окружений
- **aiogram 3** — асинхронный фреймворк для Telegram Bot API
- **SQLAlchemy 2** — ORM для работы с базой данных
- **Pydantic 2** — валидация данных и настройки
- **Loguru** — логирование

### AI / ML
- **Google Gemini API** — генерация изображений (gemini-3-pro-image-preview)
- **Google Gemini API** — генерация SEO-описаний (gemini-2.5-pro)
- **Batch API** — массовая обработка запросов к Gemini

### Интеграции
- **Google Drive API** — хранение сгенерированных изображений
- **Google Sheets API** — управление очередью изображений
- **gspread** — работа с Google Таблицами
- **httpx** — асинхронные HTTP-запросы к Gateway API

### Инфраструктура
- **SQLite** — база данных для хранения batch jobs и статусов
- **Docker** — контейнеризация
- **OAuth 2.0** — авторизация в Google сервисах

## 📁 Структура проекта

```
image_generation_bot/
├── config/              # Конфигурация (pydantic-settings)
├── models/              # SQLAlchemy модели (BatchJob, BatchJobImage)
├── migrations/          # Миграции базы данных
├── services/
│   ├── batch/           # Сервис batch-генерации через Gemini
│   ├── bot/             # Telegram бот
│   │   └── handlers/    # Обработчики команд
│   ├── gateway/         # Клиент для CMS Gateway API
│   ├── google_drive/    # Работа с Google Drive
│   ├── google_sheets/   # Работа с Google Sheets
│   ├── image_description/ # Генерация SEO-описаний
│   ├── parser/          # Парсер изображений с сайта
│   └── sync/            # Синхронизация с Gateway
├── main.py              # Точка входа
├── auth_google.py       # OAuth авторизация Google
└── pyproject.toml       # Зависимости проекта
```

## 🚀 Запуск

```bash
# Установка зависимостей
uv sync

# Авторизация в Google (первый раз)
uv run auth_google.py

# Запуск бота
uv run --env-file .env main.py
```

## ⚙️ Переменные окружения

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_AUTHORIZED_USERS=[123456789]
TELEGRAM_PROXY_URL=socks5://...  # опционально

# Gemini
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-3-pro-image-preview
GEMINI_DESCRIPTION_MODEL=gemini-2.5-pro

# Google
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id

# Database
DATABASE_URL=sqlite:///./batch_jobs.db

# Gateway (CMS API)
GATEWAY_URL=http://localhost:8002
EXTERNAL_API_KEY=your_api_key

# Other
START_URL=https://example.com/catalog
```

## 📊 Команды бота

- **🔄 Обновить изображения** — парсинг изображений с сайта
- **🎨 Отправить на генерацию** — запуск batch-генерации
- **📊 Статус** — проверка статуса batch jobs
- **📤 Загрузить фотографии** — публикация в CMS

## 📈 Workflow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Парсинг   │────▶│ Google Sheet │────▶│   Промпты   │
│   сайта     │     │  (очередь)   │     │  (ручные)   │
└─────────────┘     └──────────────┘     └──────────────┘
                                                │
                                                ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│    CMS      │◀────│ Google Drive │◀────│   Gemini    │
│  (Gateway)  │     │ (модерация)  │     │   Batch     │
└─────────────┘     └──────────────┘     └─────────────┘
```