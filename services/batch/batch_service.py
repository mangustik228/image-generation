"""
Сервис для работы с batch jobs Gemini.
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from google import genai
from google.genai import types
from loguru import logger
from sqlalchemy.orm import Session

from models.models import BatchJob, BatchJobImage, get_session_maker, init_db


BASE_PROMPT = (
    "Фотографии должны выглядеть будто сфотографировано профессиональным фотографом с качественным светом на профессиональном оборудовании."
    "На фотографии реальный объект, искажать геометрию нельзя."
    "Изображение будет использоваться для каталога мебели на сайте производителе нестандартной офисной мебели."
)

# Возможные статусы batch job
JOB_STATES = {
    "JOB_STATE_UNSPECIFIED": "Не определён",
    "JOB_STATE_PENDING": "В очереди",
    "JOB_STATE_RUNNING": "Выполняется",
    "JOB_STATE_SUCCEEDED": "Успешно завершён",
    "JOB_STATE_FAILED": "Ошибка",
    "JOB_STATE_CANCELLED": "Отменён",
    "JOB_STATE_PAUSED": "Приостановлен",
}


@dataclass
class StatusCheckResult:
    """Результат проверки статусов batch jobs."""

    total_jobs: int = 0
    jobs_pending: int = 0
    jobs_running: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    jobs_cancelled: int = 0

    total_images: int = 0
    images_succeeded: int = 0
    images_failed: int = 0
    images_pending: int = 0

    errors_grouped: dict[str, int] = field(default_factory=dict)
    processed_jobs: list[str] = field(default_factory=list)


@dataclass
class ImageTask:
    """Задача на генерацию одного изображения."""

    image_path: str
    model_name: str
    order_number: str
    custom_prompt: str
    position: int = 0
    category: str = ""
    page_url: str = ""
    source_url: str = ""


class BatchService:
    """Сервис для создания и управления batch jobs."""

    def __init__(
        self, api_key: str, database_url: str, model: str = "gemini-3-pro-image-preview"
    ):
        self.api_key = api_key
        self.database_url = database_url
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self._session_maker = get_session_maker(database_url)
        init_db(database_url)

    def _get_session(self) -> Session:
        return self._session_maker()

    def create_batch_job(self, tasks: list[ImageTask]) -> BatchJob:
        """
        Создаёт batch job из списка задач.

        Args:
            tasks: Список задач с изображениями и метаданными (каждая задача содержит custom_prompt)

        Returns:
            BatchJob сохранённый в БД
        """
        for task in tasks:
            if not Path(task.image_path).exists():
                raise FileNotFoundError(f"Файл не найден: {task.image_path}")

        batch_key = str(uuid4())
        uploaded_files = []

        for i, task in enumerate(tasks):
            uploaded_file = self.client.files.upload(
                file=str(Path(task.image_path)),
                config=types.UploadFileConfig(
                    display_name=f"batch-image-{batch_key}-{i}",
                ),
            )
            uploaded_files.append((uploaded_file, task))

        jsonl_filename = f"batch_request_{batch_key}.jsonl"
        request_keys = []

        with open(jsonl_filename, "w") as f:
            for i, (uploaded_file, task) in enumerate(uploaded_files):
                request_key = f"{batch_key}-{i}"
                request_keys.append(request_key)
                logger.debug(f"[{request_key}] Prompt: {task.custom_prompt + ". " BASE_PROMPT}")
                request_data = {
                    "key": request_key,
                    "request": {
                        "contents": [
                            {
                                "parts": [
                                    {"text": task.custom_prompt + ". " + BASE_PROMPT},
                                    {
                                        "file_data": {
                                            "file_uri": uploaded_file.uri,
                                            "mime_type": uploaded_file.mime_type,
                                        }
                                    },
                                ],
                                "role": "user",
                            }
                        ],
                        "generation_config": {
                            "responseModalities": ["TEXT", "IMAGE"],
                            "image_config": {
                                "aspect_ratio": "3:2",
                                "image_size": "2K",
                            },
                        },
                    },
                }
                f.write(json.dumps(request_data) + "\n")

        uploaded_jsonl = self.client.files.upload(
            file=jsonl_filename,
            config=types.UploadFileConfig(
                display_name=f"batch-requests-{batch_key}",
                mime_type="application/jsonl",
            ),
        )

        if uploaded_jsonl.name is None:
            raise Exception("Референс JSONL нулевой")

        source_image_names = []
        for uf, _ in uploaded_files:
            if uf.name is None:
                raise Exception("Референс изображения нулевой")
            source_image_names.append(uf.name)

        batch_job_response = self.client.batches.create(
            model=self.model,
            src=uploaded_jsonl.name,
            config={
                "display_name": f"furniture-batch-{batch_key}",
            },
        )

        Path(jsonl_filename).unlink()

        if batch_job_response.name is None:
            raise Exception("Не вернулось название batch job")

        with self._get_session() as session:
            batch_job = BatchJob(
                job_name=batch_job_response.name,
                source_image_names=source_image_names,
                jsonl_file_name=uploaded_jsonl.name,
                original_image_paths=[
                    str(Path(t.image_path).absolute()) for t in tasks
                ],
                model=self.model,
                status="PENDING",
            )
            session.add(batch_job)
            session.flush()

            for i, ((uf, task), request_key) in enumerate(
                zip(uploaded_files, request_keys)
            ):
                image_record = BatchJobImage(
                    batch_job_id=batch_job.id,
                    request_key=request_key,
                    source_image_name=uf.name,
                    original_image_path=str(Path(task.image_path).absolute()),
                    source_url=task.source_url,
                    model_name=task.model_name,
                    order_number=task.order_number,
                    position=task.position,
                    page_url=task.page_url,
                    prompt=task.custom_prompt + ". " + BASE_PROMPT,
                )
                session.add(image_record)

            session.commit()
            session.refresh(batch_job)

            return batch_job

    def get_batch_job(self, job_name: str) -> BatchJob | None:
        """Получает batch job по имени."""
        with self._get_session() as session:
            return session.query(BatchJob).filter(BatchJob.job_name == job_name).first()

    def get_pending_jobs(self) -> list[BatchJob]:
        """Получает все незавершённые batch jobs."""
        with self._get_session() as session:
            return (
                session.query(BatchJob)
                .filter(BatchJob.status.in_(["PENDING", "RUNNING"]))
                .all()
            )

    def check_job_status(self, job_name: str) -> str:
        """
        Проверяет статус batch job в Gemini API и обновляет в БД.

        Returns:
            Текущий статус job
        """
        job_info = self.client.batches.get(name=job_name)

        with self._get_session() as session:
            batch_job = (
                session.query(BatchJob).filter(BatchJob.job_name == job_name).first()
            )
            if batch_job and job_info.state:
                batch_job.status = job_info.state.name
                if job_info.state.name in ["SUCCEEDED", "FAILED", "CANCELLED"]:
                    batch_job.completed_at = datetime.now(timezone.utc)
                session.commit()

        return job_info.state.name if job_info.state else "UNKNOWN"

    def get_job_images(self, batch_job_id: str) -> list[BatchJobImage]:
        """Получает все изображения для batch job."""
        with self._get_session() as session:
            return (
                session.query(BatchJobImage)
                .filter(BatchJobImage.batch_job_id == batch_job_id)
                .all()
            )

    def update_image_result(
        self,
        request_key: str,
        result_file: str | None = None,
        error_message: str | None = None,
    ):
        """Обновляет результат для конкретного изображения."""
        with self._get_session() as session:
            image = (
                session.query(BatchJobImage)
                .filter(BatchJobImage.request_key == request_key)
                .first()
            )
            if image:
                if result_file:
                    image.result_file = result_file
                    image.status = "SUCCEEDED"
                if error_message:
                    image.error_message = error_message
                    image.status = "FAILED"
                session.commit()

    def cleanup_gemini_files(self, job_name: str):
        """Удаляет загруженные файлы из Gemini после обработки."""
        with self._get_session() as session:
            batch_job = (
                session.query(BatchJob).filter(BatchJob.job_name == job_name).first()
            )
            if not batch_job:
                return

            for file_name in batch_job.source_image_names:
                try:
                    self.client.files.delete(name=file_name)
                except Exception:
                    pass

            try:
                self.client.files.delete(name=batch_job.jsonl_file_name)
            except Exception:
                pass

    def _download_batch_results(
        self,
        session: Session,
        batch_job: BatchJob,
        drive_service,
    ) -> dict:
        """
        Проверяет статус batch job и скачивает результаты.

        Returns:
            Словарь с информацией о статусе и результатах
        """
        job_name = batch_job.job_name
        logger.info(f"Проверяю статус: {job_name}")

        job = self.client.batches.get(name=job_name)

        state = str(job.state)
        if "." in state:
            state = state.split(".")[-1]

        state_ru = JOB_STATES.get(state, state)

        result = {
            "job_name": job_name,
            "state": state,
            "state_ru": state_ru,
            "completed": False,
            "success": False,
            "output_files": [],
            "errors": [],
        }

        logger.info(f"Статус: {state_ru} ({state})")

        # Обновляем статус в БД
        if state == "JOB_STATE_SUCCEEDED":
            batch_job.status = "SUCCEEDED"
        elif state == "JOB_STATE_FAILED":
            batch_job.status = "FAILED"
        elif state == "JOB_STATE_CANCELLED":
            batch_job.status = "CANCELLED"
        elif state == "JOB_STATE_RUNNING":
            batch_job.status = "RUNNING"
        session.commit()

        # Если не завершён — просто возвращаем статус
        if state not in (
            "JOB_STATE_SUCCEEDED",
            "JOB_STATE_FAILED",
            "JOB_STATE_CANCELLED",
        ):
            logger.info("Job ещё выполняется. Проверьте позже.")
            return result

        result["completed"] = True

        if state == "JOB_STATE_FAILED":
            batch_job.error_message = "Batch job завершился с ошибкой"
            session.commit()
            result["error"] = batch_job.error_message
            logger.error(f"Ошибка: {result['error']}")
            return result

        if state == "JOB_STATE_CANCELLED":
            batch_job.error_message = "Batch job был отменён"
            session.commit()
            result["error"] = batch_job.error_message
            logger.warning(f"Отменён: {result['error']}")
            return result

        # Job успешен — извлекаем результаты
        result["success"] = True
        logger.info("Job успешно завершён. Извлекаю результаты...")

        if not hasattr(job, "dest") or not job.dest:
            result["error"] = "Нет информации о результатах (dest отсутствует)"
            return result

        dest = job.dest

        # Получаем изображения для этого batch job
        images = (
            session.query(BatchJobImage)
            .filter(BatchJobImage.batch_job_id == batch_job.id)
            .all()
        )
        images_by_key = {img.request_key: img for img in images}

        # Результаты в файле (основной вариант)
        if hasattr(dest, "file_name") and dest.file_name:
            result_file_name = dest.file_name
            logger.info(f"Результаты в файле: {result_file_name}")
            result = self._download_and_process_file(
                result_file_name, drive_service, result, images_by_key, session
            )
        # Результаты inline
        elif hasattr(dest, "inlined_responses") and dest.inlined_responses:
            logger.info("Результаты найдены inline")
            result = self._process_inline_responses(
                dest.inlined_responses, drive_service, result, images_by_key, session
            )
        else:
            result["errors"].append(
                {"key": "unknown", "error": "Неизвестный формат результатов"}
            )

        return result

    def _process_inline_responses(
        self,
        inlined_responses,
        drive_service,
        result: dict,
        images_by_key: dict[str, BatchJobImage],
        session: Session,
    ) -> dict:
        """Обрабатывает inline результаты."""
        for response in inlined_responses:
            response_key = getattr(response, "key", None)
            if not response_key:
                continue

            image_record = images_by_key.get(response_key)

            if hasattr(response, "response") and response.response:
                resp = response.response

                if hasattr(resp, "candidates") and resp.candidates:
                    for candidate in resp.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts:
                                # Изображение
                                if hasattr(part, "inline_data") and part.inline_data:
                                    if image_record:
                                        output_filename = (
                                            image_record.get_output_filename()
                                        )
                                        image_bytes = base64.b64decode(
                                            part.inline_data.data
                                        )

                                        file_id = drive_service.upload_file(
                                            image_bytes, output_filename
                                        )

                                        if file_id:
                                            image_record.result_file = file_id
                                            image_record.status = "SUCCEEDED"
                                            session.commit()

                                            result["output_files"].append(
                                                {
                                                    "key": response_key,
                                                    "file_id": file_id,
                                                }
                                            )
                                            logger.info(
                                                f"[{response_key}] Изображение загружено в Google Drive: {file_id}"
                                            )
                                        else:
                                            image_record.error_message = (
                                                "Ошибка загрузки в Google Drive"
                                            )
                                            image_record.status = "FAILED"
                                            session.commit()
                                            result["errors"].append(
                                                {
                                                    "key": response_key,
                                                    "error": "Ошибка загрузки в Google Drive",
                                                }
                                            )

            # Проверяем на ошибки
            if hasattr(response, "error") and response.error:
                error_msg = str(response.error)
                if image_record:
                    image_record.error_message = error_msg
                    image_record.status = "FAILED"
                    session.commit()
                result["errors"].append({"key": response_key, "error": error_msg})
                logger.error(f"[{response_key}] Ошибка: {error_msg}")

        return result

    def _download_and_process_file(
        self,
        file_name: str,
        drive_service,
        result: dict,
        images_by_key: dict[str, BatchJobImage],
        session: Session,
    ) -> dict:
        """Скачивает файл результатов и загружает изображения в Google Drive."""
        try:
            logger.info(f"Скачиваю файл результатов: {file_name}")
            file_content_bytes = self.client.files.download(file=file_name)
            file_content = file_content_bytes.decode("utf-8")

            for line in file_content.strip().split("\n"):
                if not line:
                    continue

                response_data = json.loads(line)
                response_key = response_data.get("key")
                if not response_key:
                    continue

                image_record = images_by_key.get(response_key)
                logger.info(f"Обрабатываю ответ с ключом: {response_key}")

                has_image = False

                if "response" in response_data:
                    resp = response_data["response"]

                    if "candidates" in resp:
                        for candidate in resp["candidates"]:
                            if (
                                "content" in candidate
                                and "parts" in candidate["content"]
                            ):
                                for part in candidate["content"]["parts"]:
                                    # Изображение (inline_data с base64)
                                    if "inline_data" in part or "inlineData" in part:
                                        inline_data = part.get(
                                            "inline_data"
                                        ) or part.get("inlineData")
                                        if inline_data and image_record:
                                            output_filename = (
                                                image_record.get_output_filename()
                                            )
                                            image_bytes = base64.b64decode(
                                                inline_data["data"]
                                            )

                                            file_id = drive_service.upload_file(
                                                image_bytes, output_filename
                                            )

                                            if file_id:
                                                image_record.result_file = file_id
                                                image_record.status = "SUCCEEDED"
                                                session.commit()

                                                result["output_files"].append(
                                                    {
                                                        "key": response_key,
                                                        "file_id": file_id,
                                                    }
                                                )
                                                logger.info(
                                                    f"[{response_key}] Изображение загружено в Google Drive: {file_id}"
                                                )
                                                has_image = True
                                            else:
                                                image_record.error_message = (
                                                    "Ошибка загрузки в Google Drive"
                                                )
                                                image_record.status = "FAILED"
                                                session.commit()
                                                result["errors"].append(
                                                    {
                                                        "key": response_key,
                                                        "error": "Ошибка загрузки в Google Drive",
                                                    }
                                                )

                # Логируем если изображение отсутствует
                if not has_image and "error" not in response_data:
                    logger.warning(f"[{response_key}] ⚠️ Изображение НЕ сгенерировано!")
                    if image_record:
                        image_record.error_message = "Изображение не сгенерировано"
                        image_record.status = "FAILED"
                        session.commit()
                    result["errors"].append(
                        {"key": response_key, "error": "Изображение не сгенерировано"}
                    )

                # Проверяем на ошибки в ответе
                if "error" in response_data:
                    error_msg = str(response_data["error"])
                    if image_record:
                        image_record.error_message = error_msg
                        image_record.status = "FAILED"
                        session.commit()
                    result["errors"].append({"key": response_key, "error": error_msg})
                    logger.error(f"[{response_key}] Ошибка в ответе: {error_msg}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при скачивании файла: {error_msg}")

            if "40 characters" in error_msg or "INVALID_ARGUMENT" in error_msg:
                result["errors"].append(
                    {
                        "key": "download",
                        "error": f"Баг Gemini API: ID файла результата слишком длинный. "
                        f"Файл: {file_name}. "
                        f"Это известная проблема: https://github.com/googleapis/python-genai/issues/1759",
                    }
                )
            else:
                result["errors"].append(
                    {"key": "download", "error": f"Ошибка скачивания: {error_msg}"}
                )

        return result

    def check_and_download_results(
        self,
        drive_service,
        statuses: list[str] | None = None,
    ) -> StatusCheckResult:
        """
        Проверяет статусы batch jobs и скачивает результаты.

        Args:
            drive_service: GoogleDriveService для загрузки результатов
            statuses: Список статусов для проверки (по умолчанию PENDING и RUNNING)

        Returns:
            StatusCheckResult со статистикой
        """
        if statuses is None:
            statuses = ["PENDING", "RUNNING"]

        result = StatusCheckResult()

        with self._get_session() as session:
            jobs = session.query(BatchJob).filter(BatchJob.status.in_(statuses)).all()

            result.total_jobs = len(jobs)

            for batch_job in jobs:
                result.processed_jobs.append(batch_job.job_name)

                try:
                    job_result = self._download_batch_results(
                        session, batch_job, drive_service
                    )

                    state = job_result.get("state", "")
                    if state == "JOB_STATE_PENDING":
                        result.jobs_pending += 1
                    elif state == "JOB_STATE_RUNNING":
                        result.jobs_running += 1
                    elif state == "JOB_STATE_SUCCEEDED":
                        result.jobs_succeeded += 1
                    elif state == "JOB_STATE_FAILED":
                        result.jobs_failed += 1
                    elif state == "JOB_STATE_CANCELLED":
                        result.jobs_cancelled += 1

                    for error in job_result.get("errors", []):
                        error_msg = error.get("error", "Unknown error")
                        if error_msg in result.errors_grouped:
                            result.errors_grouped[error_msg] += 1
                        else:
                            result.errors_grouped[error_msg] = 1

                except Exception as e:
                    result.jobs_failed += 1
                    error_msg = str(e)
                    if error_msg in result.errors_grouped:
                        result.errors_grouped[error_msg] += 1
                    else:
                        result.errors_grouped[error_msg] = 1

            # Подсчёт статистики по изображениям
            all_images = session.query(BatchJobImage).all()
            result.total_images = len(all_images)

            for img in all_images:
                if img.status == "SUCCEEDED":
                    result.images_succeeded += 1
                elif img.status == "FAILED":
                    result.images_failed += 1
                else:
                    result.images_pending += 1

        return result

    def get_overall_statistics(self) -> StatusCheckResult:
        """
        Получает общую статистику по всем batch jobs и изображениям.

        Returns:
            StatusCheckResult со статистикой
        """
        result = StatusCheckResult()

        with self._get_session() as session:
            all_jobs = session.query(BatchJob).all()
            result.total_jobs = len(all_jobs)

            for job in all_jobs:
                if job.status == "PENDING":
                    result.jobs_pending += 1
                elif job.status == "RUNNING":
                    result.jobs_running += 1
                elif job.status == "SUCCEEDED":
                    result.jobs_succeeded += 1
                elif job.status == "FAILED":
                    result.jobs_failed += 1
                elif job.status == "CANCELLED":
                    result.jobs_cancelled += 1

            all_images = session.query(BatchJobImage).all()
            result.total_images = len(all_images)

            for img in all_images:
                if img.status == "SUCCEEDED":
                    result.images_succeeded += 1
                elif img.status == "FAILED":
                    result.images_failed += 1
                    if img.error_message:
                        if img.error_message in result.errors_grouped:
                            result.errors_grouped[img.error_message] += 1
                        else:
                            result.errors_grouped[img.error_message] = 1
                else:
                    result.images_pending += 1

        return result
