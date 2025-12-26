"""
Миграция: удаление полей изображений из таблицы batch_jobs.

Эти поля относятся к отдельным изображениям (BatchJobImage), а не к batch job:
- prompt
- model_name
- order_number
- position
- category

Дата: 2024-12-26
"""

from sqlalchemy import text

from config import settings
from models.models import get_engine


COLUMNS_TO_REMOVE = ["prompt", "model_name", "order_number", "position", "category"]


def upgrade(database_url: str):
    """Удаляет колонки изображений из batch_jobs."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        for column in COLUMNS_TO_REMOVE:
            try:
                conn.execute(text(f"ALTER TABLE batch_jobs DROP COLUMN {column}"))
                print(f"✓ Удалена колонка {column}")
            except Exception as e:
                print(f"⚠ Колонка {column} не существует или уже удалена: {e}")
        conn.commit()
    print("✓ Миграция завершена")


def downgrade(database_url: str):
    """Восстанавливает колонки (с пустыми значениями)."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE batch_jobs ADD COLUMN prompt TEXT"))
        conn.execute(text("ALTER TABLE batch_jobs ADD COLUMN model_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE batch_jobs ADD COLUMN order_number VARCHAR(100)"))
        conn.execute(text("ALTER TABLE batch_jobs ADD COLUMN position INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE batch_jobs ADD COLUMN category VARCHAR(255) DEFAULT ''"))
        conn.commit()
    print("✓ Колонки восстановлены")


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
