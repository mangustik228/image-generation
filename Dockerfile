# Dockerfile
FROM python:3.13-slim

# Установка uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Создание рабочей директории
WORKDIR /app

# Копирование файлов конфигурации
COPY pyproject.toml uv.lock ./

# Установка зависимостей
RUN uv sync --frozen

# Копирование исходного кода
COPY . .

# Запуск бота
CMD ["uv", "run", "main.py"]