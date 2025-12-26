from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class BatchJob(Base):
    """Информация о batch job для генерации изображений."""

    __tablename__ = "batch_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    job_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_image_names: Mapped[list[str]] = mapped_column(JSON)
    jsonl_file_name: Mapped[str] = mapped_column(String(255))

    original_image_paths: Mapped[list[str]] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class BatchJobImage(Base):
    """Отдельное изображение в batch job (для сопоставления результатов)."""

    __tablename__ = "batch_job_images"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    batch_job_id: Mapped[str] = mapped_column(String(36), index=True)
    request_key: Mapped[str] = mapped_column(String(100), index=True)
    source_image_name: Mapped[str] = mapped_column(String(255))
    original_image_path: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    model_name: Mapped[str] = mapped_column(String(255))
    order_number: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(default=0)
    page_url: Mapped[str] = mapped_column(String(500), default="", nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    result_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    alt: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_cms_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    published: Mapped[bool] = mapped_column(default=False)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def get_output_filename(self) -> str:
        """
        Генерирует имя файла для сохранения в Google Drive.
        Формат: {slug}_{order_number}_{position}_{uuid}.jpg
        """
        from slugify import slugify

        slug = slugify(self.model_name, lowercase=True)
        uuid_short = str(uuid4()).split("-")[0]
        return f"{slug}_{self.order_number}_{self.position}_{uuid_short}.jpg"

    def get_cms_filename(self) -> str:
        """
        Генерирует имя файла для загрузки в CMS (без order_number).
        Формат: {slug}-{uuid}.jpg
        """
        from slugify import slugify

        slug = slugify(self.model_name, lowercase=True)
        uuid_short = str(uuid4()).split("-")[0]
        return f"{slug}-{uuid_short}.jpg"

    def get_collection_path(self) -> str | None:
        """Возвращает путь коллекции из page_url (без последнего сегмента)."""
        if not self.page_url:
            return None
        # Убираем trailing slash и берём путь без последнего сегмента
        path = self.page_url.rstrip("/")
        return "/".join(path.split("/")[:-1]) or None


def get_engine(database_url: str):
    return create_engine(database_url, echo=False)


def get_session_maker(database_url: str):
    engine = get_engine(database_url)
    return sessionmaker(bind=engine)


def init_db(database_url: str):
    """Создаёт все таблицы в базе данных."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
