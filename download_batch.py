"""
Ручная повторная загрузка результатов batch job в Google Drive.

Используется, если автоматическая загрузка через бот завершилась некорректно
(например, упала сеть, истёк токен Drive, часть изображений не сохранилась).

Запуск:
    uv run download_batch.py --batch <job_name>
    uv run download_batch.py --batch <job_name> --all

По умолчанию переобрабатываются только изображения без `result_file`
(т.е. PENDING и FAILED). Флаг `--all` форсирует повторную загрузку всех
изображений job — даже уже SUCCEEDED. ВНИМАНИЕ: в этом режиме в Drive
появятся дубликаты, т.к. имя файла генерируется с новым UUID.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from config import settings
from models.models import BatchJob, BatchJobImage
from services.batch import BatchService
from services.google_drive import GoogleDriveService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Повторная ручная загрузка результатов batch job в Google Drive.",
    )
    parser.add_argument(
        "--batch",
        required=True,
        help="job_name batch job (то, что возвращает handler / хранится в BatchJob.job_name).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Перезагрузить все изображения, включая уже SUCCEEDED (создаст дубликаты в Drive).",
    )
    return parser.parse_args()


def _print_summary(job_name: str, result: dict) -> None:
    logger.info("=" * 60)
    logger.info(f"Job: {job_name}")
    logger.info(f"State: {result.get('state_ru')} ({result.get('state')})")
    logger.info(f"Completed: {result.get('completed')}")
    logger.info(f"Success: {result.get('success')}")
    logger.info(f"Загружено файлов: {len(result.get('output_files', []))}")
    errors = result.get("errors", [])
    logger.info(f"Ошибок: {len(errors)}")
    for err in errors:
        logger.error(f"  [{err.get('key')}] {err.get('error')}")
    logger.info("=" * 60)


def main() -> int:
    args = _parse_args()
    job_name: str = args.batch
    redo_all: bool = args.all

    batch_service = BatchService(
        api_key=settings.gemini.api_key,
        database_url=settings.database.url,
        model=settings.gemini.model,
    )
    drive_service = GoogleDriveService(
        folder_id=settings.google.drive_folder_id,
    )

    with batch_service._get_session() as session:
        batch_job = (
            session.query(BatchJob).filter(BatchJob.job_name == job_name).first()
        )
        if batch_job is None:
            logger.error(f"Batch job не найден в БД: {job_name}")
            return 1

        logger.info(
            f"Найден batch job: id={batch_job.id} status={batch_job.status} "
            f"created_at={batch_job.created_at}"
        )

        if not redo_all:
            # Сбрасываем статус только тех изображений, для которых ещё нет result_file,
            # чтобы _download_batch_results не пытался их перезаписать,
            # а заодно сбрасываем error_message. Логика в _download_and_process_file
            # уже корректно обновит запись при успешной загрузке.
            #
            # Чтобы избежать дубликатов уже успешных изображений, временно
            # подменяем images_by_key — вместо этого вызываем приватный метод
            # _download_and_process_file напрямую только для нужных ключей.
            images_to_retry = (
                session.query(BatchJobImage)
                .filter(
                    BatchJobImage.batch_job_id == batch_job.id,
                    BatchJobImage.result_file.is_(None),
                )
                .all()
            )
            if not images_to_retry:
                logger.info(
                    "Нет изображений для повторной загрузки (все уже имеют result_file). "
                    "Запустите с --all, чтобы форсировать."
                )
                return 0
            logger.info(
                f"К повторной загрузке: {len(images_to_retry)} из "
                f"{len(batch_service.get_job_images(batch_job.id))} изображений."
            )

            # Сбрасываем статус job, чтобы метод реально пошёл в API за результатами
            # (он проверяет state из Gemini, статус в БД не влияет на ветку скачивания).
            result = batch_service._download_batch_results(
                session, batch_job, drive_service
            )
            # Отфильтруем output_files / errors по нашему множеству ключей
            retry_keys = {img.request_key for img in images_to_retry}
            result["output_files"] = [
                f for f in result.get("output_files", []) if f.get("key") in retry_keys
            ]
            result["errors"] = [
                e for e in result.get("errors", []) if e.get("key") in retry_keys
            ]
        else:
            logger.warning(
                "Режим --all: будут перезагружены ВСЕ изображения, включая "
                "уже SUCCEEDED. В Google Drive появятся дубликаты."
            )
            # Чтобы _download_and_process_file перезаписал result_file у SUCCEEDED,
            # сбрасываем их состояние локально (без коммита глобального reset job).
            images = (
                session.query(BatchJobImage)
                .filter(BatchJobImage.batch_job_id == batch_job.id)
                .all()
            )
            for img in images:
                img.result_file = None
                img.error_message = None
                img.status = "PENDING"
            session.commit()
            result = batch_service._download_batch_results(
                session, batch_job, drive_service
            )

    _print_summary(job_name, result)
    # Возвращаем ненулевой код, если были ошибки и ни одного успеха
    if result.get("errors") and not result.get("output_files"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
