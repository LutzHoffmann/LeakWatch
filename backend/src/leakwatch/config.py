"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings sourced from environment / `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://leakwatch:leakwatch@localhost:5432/leakwatch",
    )

    # Redis / ARQ
    redis_url: str = Field(default="redis://localhost:6379/0")

    # LLM (OpenRouter)
    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    llm_model: str = Field(default="z-ai/glm-5.2")
    llm_timeout_seconds: float = Field(default=60.0)

    # Watchers
    github_token: str = Field(default="")
    github_gist_poll_interval_seconds: int = Field(default=300)
    pastebin_poll_interval_seconds: int = Field(default=300)

    # Alerting — Email (Resend)
    resend_api_key: str = Field(default="")
    alert_from_email: str = Field(default="alerts@leakwatch.local")
    alert_to_email: str = Field(default="")

    # Alerting — Telegram
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # Alerting — generic webhook
    alert_webhook_url: str = Field(default="")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key and self.alert_to_email)

    @property
    def webhook_enabled(self) -> bool:
        return bool(self.alert_webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
