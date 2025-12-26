from email.charset import BASE64

from pydantic_settings import BaseSettings, SettingsConfigDict


class _Telegram(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")
    bot_token: str
    authorized_users: list[int]


class _GEMINI(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEMINI_")
    api_key: str
    model: str = "gemini-3-pro-image-preview"
    description_model: str = "gemini-2.5-pro"


class _GOOGLE(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOOGLE_")
    credentials_path: str = "credentials.json"
    drive_folder_id: str = ""


class _Database(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_")
    url: str = "sqlite:///./batch_jobs.db"


class _Gateway(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_")
    url: str = "http://localhost:8002"


class _CDN(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CDN_")
    url: str = "http://cdn.localhost"


class Settings(BaseSettings):
    telegram: _Telegram = _Telegram()  # type: ignore
    gemini: _GEMINI = _GEMINI()  # type: ignore
    google: _GOOGLE = _GOOGLE()  # type: ignore
    gateway: _Gateway = _Gateway()  # type: ignore
    database: _Database = _Database()
    cdn: _CDN = _CDN()  # type: ignore
    start_url: str
    external_api_key: str = "my_api_key"
