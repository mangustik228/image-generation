"""
Скрипт для первичной OAuth авторизации Google Drive.
Запустите один раз локально для получения token.json.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]
OAUTH_CREDENTIALS_FILE = "auth_credentials.json"
TOKEN_FILE = "token.json"


def authenticate():
    """Выполняет OAuth авторизацию и сохраняет токен."""
    creds = None

    # Проверяем существующий токен
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Если токен невалидный или отсутствует
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Обновляю токен...")
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CREDENTIALS_FILE):
                print(f"Ошибка: файл {OAUTH_CREDENTIALS_FILE} не найден!")
                print("Скачайте OAuth credentials из Google Cloud Console")
                return None

            print("Открываю браузер для авторизации...")
            flow = InstalledAppFlow.from_client_secrets_file(
                OAUTH_CREDENTIALS_FILE, SCOPES
            )
            # Используем консольный режим, если браузер недоступен
            try:
                creds = flow.run_local_server(port=0, open_browser=False)
            except Exception:
                creds = flow.run_console()

        # Сохраняем токен
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print(f"Токен сохранён в {TOKEN_FILE}")

    print("Авторизация успешна!")
    return creds


if __name__ == "__main__":
    authenticate()
