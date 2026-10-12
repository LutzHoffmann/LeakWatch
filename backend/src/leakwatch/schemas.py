"""Pydantic schemas (DTOs) used across watchers, analyzer, matcher and alerter."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CredentialKind(StrEnum):
    EMAIL = "email"
    PASSWORD = "password"  # noqa: S105
    URL = "url"
    WALLET = "wallet"


class RawItem(BaseModel):
    """A raw text blob fetched from a source by a watcher."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    external_id: str
    url: str
    content: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Credential(BaseModel):
    """A credential extracted from a raw item by the LLM analyzer."""

    model_config = ConfigDict(from_attributes=True)

    kind: CredentialKind
    value: str
    context: str = ""
    # When the analyzer extracts an explicit email+password pair, both the
    # EMAIL and the PASSWORD credential share the same ``pair_id`` so the UI
    # can reconstruct the combination. None for standalone credentials.
    pair_id: str | None = None


class EmailPasswordPair(BaseModel):
    """An explicit email + password combination found in raw leak text."""

    email: str
    password: str  # noqa: S105


class LLMExtractionResult(BaseModel):
    """Structured JSON contract returned by the LLM extraction prompt."""

    pairs: list[EmailPasswordPair] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    passwords: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    wallets: list[str] = Field(default_factory=list)


class Match(BaseModel):
    """A match between a credential and a monitored user domain/email."""

    model_config = ConfigDict(from_attributes=True)

    credential: Credential
    domain_value: str
    reason: str = ""


class AlertPayload(BaseModel):
    """Payload delivered to an alerting channel."""

    channel: str
    match: Match
    message: str
