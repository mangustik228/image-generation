"""
Миграция: добавление колонок user_id и notified в таблицу batch_jobs.
Используется для авто-уведомления Telegram-пользователя о завершении batch job.
"""

from sqlalchemy import text

from config import settings
from models.models import get_engine


def upgrade(database_url: str):
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE batch_jobs ADD COLUMN user_id BIGINT"))
        conn.execute(
            text(
                "ALTER TABLE batch_jobs ADD COLUMN notified BOOLEAN NOT NULL DEFAULT 0"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_batch_jobs_user_id ON batch_jobs(user_id)")
        )
        conn.commit()
    print("✓ Добавлены колонки user_id и notified в batch_jobs")


def downgrade(database_url: str):
    engine = get_engine(database_url)
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_batch_jobs_user_id"))
        conn.execute(text("ALTER TABLE batch_jobs DROP COLUMN notified"))
        conn.execute(text("ALTER TABLE batch_jobs DROP COLUMN user_id"))
        conn.commit()
    print("✓ Удалены колонки user_id и notified из batch_jobs")


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
