"""
Миграция: добавление колонки image_cms_id в таблицу batch_job_images.
Дата: 2024-12-26
"""

from sqlalchemy import text

from config import settings
from models.models import get_engine


def upgrade(database_url: str):
    """Добавляет колонку image_cms_id."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE batch_job_images ADD COLUMN image_cms_id VARCHAR(100) NULL"
            )
        )
        conn.commit()
    print("✓ Добавлена колонка image_cms_id в batch_job_images")


def downgrade(database_url: str):
    """Удаляет колонку image_cms_id."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE batch_job_images DROP COLUMN image_cms_id"))
        conn.commit()
    print("✓ Удалена колонка image_cms_id из batch_job_images")


if __name__ == "__main__":
    import os

    database_url = settings.database.url
    if not database_url:
        print("Ошибка: DATABASE_URL не задан")
        exit(1)

    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade(database_url)
    else:
        upgrade(database_url)
