"""
Скрипт для скачивания изображений из batch job в папку data.
"""

import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()

BATCH_NAME = "batches/rx3akmkdgo7tm3ycyhrkt7k4wem6k8n9z19z"
OUTPUT_DIR = Path("data/batch_images")


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY не найден в переменных окружения")
        return

    client = genai.Client(api_key=api_key)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Получаю информацию о batch: {BATCH_NAME}")
    job = client.batches.get(name=BATCH_NAME)

    print(f"Статус: {job.state}")
    print(f"Модель: {job.model}")

    if not hasattr(job, "dest") or not job.dest:
        print("Нет информации о результатах (dest отсутствует)")
        return

    dest = job.dest

    # Результаты в файле
    if hasattr(dest, "file_name") and dest.file_name:
        result_file_name = dest.file_name
        print(f"Результаты в файле: {result_file_name}")

        try:
            file_content_bytes = client.files.download(file=result_file_name)
            file_content = file_content_bytes.decode("utf-8")

            count = 0
            for line in file_content.strip().split("\n"):
                if not line:
                    continue

                response_data = json.loads(line)
                response_key = response_data.get("key", f"unknown_{count}")
                print(f"Обрабатываю: {response_key}")

                if "response" in response_data:
                    resp = response_data["response"]

                    if "candidates" in resp:
                        for candidate in resp["candidates"]:
                            if (
                                "content" in candidate
                                and "parts" in candidate["content"]
                            ):
                                for part in candidate["content"]["parts"]:
                                    if "inline_data" in part or "inlineData" in part:
                                        inline_data = part.get(
                                            "inline_data"
                                        ) or part.get("inlineData")
                                        if inline_data and "data" in inline_data:
                                            image_bytes = base64.b64decode(
                                                inline_data["data"]
                                            )

                                            mime_type = inline_data.get(
                                                "mime_type", "image/png"
                                            )
                                            ext = "png" if "png" in mime_type else "jpg"

                                            output_path = (
                                                OUTPUT_DIR / f"{response_key}.{ext}"
                                            )
                                            output_path.write_bytes(image_bytes)
                                            print(f"  ✓ Сохранено: {output_path}")
                                            count += 1

                if "error" in response_data:
                    print(f"  ✗ Ошибка: {response_data['error']}")

            print(f"\nВсего сохранено изображений: {count}")

        except Exception as e:
            print(f"Ошибка при скачивании: {e}")

    # Результаты inline
    elif hasattr(dest, "inlined_responses") and dest.inlined_responses:
        print("Результаты найдены inline")
        count = 0

        for response in dest.inlined_responses:
            response_key = getattr(response, "key", f"unknown_{count}")
            print(f"Обрабатываю: {response_key}")

            if hasattr(response, "response") and response.response:
                resp = response.response

                if hasattr(resp, "candidates") and resp.candidates:
                    for candidate in resp.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts:
                                if hasattr(part, "inline_data") and part.inline_data:
                                    image_bytes = base64.b64decode(
                                        part.inline_data.data
                                    )

                                    mime_type = getattr(
                                        part.inline_data, "mime_type", "image/png"
                                    )
                                    ext = "png" if "png" in mime_type else "jpg"

                                    output_path = OUTPUT_DIR / f"{response_key}.{ext}"
                                    output_path.write_bytes(image_bytes)
                                    print(f"  ✓ Сохранено: {output_path}")
                                    count += 1

            if hasattr(response, "error") and response.error:
                print(f"  ✗ Ошибка: {response.error}")

        print(f"\nВсего сохранено изображений: {count}")

    else:
        print("Неизвестный формат результатов")
        print(f"dest: {dest}")


if __name__ == "__main__":
    main()
