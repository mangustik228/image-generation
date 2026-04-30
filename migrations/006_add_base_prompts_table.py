"""
Миграция: создание таблицы base_prompts и вставка первого базового промпта.
"""

from uuid import uuid4

from sqlalchemy import text

from config import settings
from models.models import get_engine

INITIAL_PROMPT = (
    "Фотографии должны выглядеть будто сфотографировано профессиональным фотографом с качественным светом на профессиональном оборудовании."
    "На фотографии реальный объект, искажать геометрию нельзя."
    "Изображение будет использоваться для каталога мебели на сайте производителе нестандартной офисной мебели."
)


def upgrade(database_url: str):
    """Создаёт таблицу base_prompts и вставляет начальный промпт."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS base_prompts (
                    id VARCHAR(36) PRIMARY KEY,
                    text TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO base_prompts (id, text, is_active) VALUES (:id, :text, TRUE)"
            ),
            {"id": str(uuid4()), "text": INITIAL_PROMPT},
        )
        conn.commit()
    print("✓ Создана таблица base_prompts и вставлен начальный промпт")


def downgrade(database_url: str):
    """Удаляет таблицу base_prompts."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS base_prompts"))
        conn.commit()
    print("✓ Удалена таблица base_prompts")


if __name__ == "__main__":
    import sys

    database_url = settings.database.url
    if not database_url:
        print("Ошибка: DATABASE_URL не задан")
        exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade(database_url)
    else:
        upgrade(database_url)
