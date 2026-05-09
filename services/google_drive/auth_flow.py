"""Helpers for re-running Google OAuth flow from the bot when token expires."""

import os
from typing import Optional
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow
from loguru import logger

SCOPES = ["https://www.googleapis.com/auth/drive"]
OAUTH_CREDENTIALS_FILE = "auth_credentials.json"
TOKEN_FILE = "token.json"
REDIRECT_URI = "http://localhost"

_active_flow: Optional[Flow] = None


def start_auth_flow() -> str:
    """Start a new OAuth flow and return the authorization URL.

    The user must open the URL in a browser, authorize the app, then copy the
    resulting redirect URL (or just the ``code`` query parameter) and pass it
    to :func:`complete_auth_flow`.
    """
    global _active_flow

    if not os.path.exists(OAUTH_CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Файл {OAUTH_CREDENTIALS_FILE} не найден. "
            "Скачайте OAuth credentials из Google Cloud Console."
        )

    flow = Flow.from_client_secrets_file(
        OAUTH_CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    _active_flow = flow

    # Удаляем старый протухший токен, чтобы не мешал
    try:
        os.remove(TOKEN_FILE)
        logger.info(f"Removed expired token file: {TOKEN_FILE}")
    except FileNotFoundError:
        pass

    logger.info("Started new Google OAuth flow")
    return auth_url


def complete_auth_flow(response: str) -> None:
    """Finish the OAuth flow using the authorization code or full redirect URL."""
    global _active_flow

    if _active_flow is None:
        raise RuntimeError(
            "Нет активного процесса авторизации. Запустите заново."
        )

    code = (response or "").strip()
    if not code:
        raise ValueError("Пустой ответ.")

    # Если пришёл целый URL — вытаскиваем параметр code
    if code.startswith("http://") or code.startswith("https://"):
        qs = parse_qs(urlparse(code).query)
        code_list = qs.get("code")
        if not code_list:
            raise ValueError("В URL не найден параметр `code`.")
        code = code_list[0]

    _active_flow.fetch_token(code=code)
    creds = _active_flow.credentials

    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    _active_flow = None
    logger.info(f"OAuth token saved to {TOKEN_FILE}")


def cancel_auth_flow() -> None:
    global _active_flow
    _active_flow = None


def is_auth_flow_active() -> bool:
    return _active_flow is not None
