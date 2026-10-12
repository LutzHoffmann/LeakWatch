"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(v: object) -> object:
    """Allow list settings to be set as a comma-separated env string."""
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


class Settings(BaseSettings):
    """Strongly-typed settings sourced from environment / `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://leakwatch:leakwatch@localhost:5432/leakwatch",
    )

    # Redis / ARQ
    redis_url: str = Field(default="redis://localhost:6379/0")

    # LLM — provider-agnostic (OpenRouter or ZAI/Zhipu directly).
    # Both LLM_* and the legacy OPENROUTER_* env var names are accepted.
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("llm_api_key", "openrouter_api_key"),
    )
    llm_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("llm_base_url", "openrouter_base_url"),
    )
    llm_model: str = Field(
        default="z-ai/glm-5.2",
        validation_alias=AliasChoices("llm_model"),
    )
    llm_timeout_seconds: float = Field(default=60.0)

    # Watchers
    github_token: str = Field(default="")
    github_gist_poll_interval_seconds: int = Field(default=300)
    pastebin_poll_interval_seconds: int = Field(default=300)

    # GitHub Code Search watcher — queries run against the public code search
    # API. Keep these targeted; broad queries are noisy and rate-limited.
    github_code_search_queries: Annotated[list[str], BeforeValidator(_split_csv)] = Field(
        default_factory=lambda: [
            "password",
            "api_key",
            "BEGIN PRIVATE KEY",
        ],
    )
    github_code_max_results: int = Field(default=20)

    # Intelligence X — selector search (email/domain/IP) across leaks, pastes
    # and darknet sources. API access requires an IntelX subscription.
    intelx_api_key: str = Field(default="")
    intelx_base_url: str = Field(default="https://2.intelx.io")

    # Pwned Passwords — free, keyless SHA-1 range search (k-anonymity).
    pwned_base_url: str = Field(default="https://api.pwnedpasswords.com")

    # API server (FastAPI) — used by the Next.js frontend.
    api_cors_origins: Annotated[list[str], BeforeValidator(_split_csv)] = Field(
        default_factory=lambda: ["http://localhost:3000"],
    )

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
