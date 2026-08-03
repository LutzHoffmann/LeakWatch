"""Alerter — delivers match notifications via email (Resend), Telegram and webhooks."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from .config import get_settings
from .schemas import AlertPayload, Match

log = structlog.get_logger(__name__)


class Alerter:
    """Send alerts for matches through all enabled channels."""

    def __init__(self, settings: Any | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _format_message(self, match: Match) -> str:
        return (
            f"LeakWatch alert\n"
            f"  kind: {match.credential.kind}\n"
            f"  value: {match.credential.value}\n"
            f"  monitored: {match.domain_value}\n"
            f"  reason: {match.reason}"
        )

    async def send(self, match: Match) -> list[AlertPayload]:
        message = self._format_message(match)
        sent: list[AlertPayload] = []
        if self._settings.email_enabled:
            sent.append(await self._send_email(match, message))
        if self._settings.telegram_enabled:
            sent.append(await self._send_telegram(match, message))
        if self._settings.webhook_enabled:
            sent.append(await self._send_webhook(match, message))
        if not sent:
            log.info("alert_no_channel_enabled", match=match.model_dump())
        return sent

    async def _send_email(self, match: Match, message: str) -> AlertPayload:
        try:
            import resend  # noqa: PLC0415

            resend.api_key = self._settings.resend_api_key
            params: dict[str, Any] = {
                "from": self._settings.alert_from_email,
                "to": [self._settings.alert_to_email],
                "subject": f"LeakWatch alert: {match.domain_value}",
                "text": message,
            }
            resend.Emails.send(params)  # type: ignore[arg-type]
            return AlertPayload(channel="email", match=match, message=message)
        except Exception as exc:  # noqa: BLE001
            log.warning("email_alert_failed", error=str(exc))
            return AlertPayload(channel="email", match=match, message=f"failed: {exc}")

    async def _send_telegram(self, match: Match, message: str) -> AlertPayload:
        client = await self._get_client()
        url = (
            f"https://api.telegram.org/bot{self._settings.telegram_bot_token}/sendMessage"
        )
        try:
            resp = await client.post(
                url,
                json={
                    "chat_id": self._settings.telegram_chat_id,
                    "text": message,
                },
            )
            resp.raise_for_status()
            return AlertPayload(channel="telegram", match=match, message=message)
        except httpx.HTTPError as exc:
            log.warning("telegram_alert_failed", error=str(exc))
            return AlertPayload(channel="telegram", match=match, message=f"failed: {exc}")

    async def _send_webhook(self, match: Match, message: str) -> AlertPayload:
        client = await self._get_client()
        try:
            resp = await client.post(
                self._settings.alert_webhook_url,
                json={"message": message, "match": match.model_dump(mode="json")},
            )
            resp.raise_for_status()
            return AlertPayload(channel="webhook", match=match, message=message)
        except httpx.HTTPError as exc:
            log.warning("webhook_alert_failed", error=str(exc))
            return AlertPayload(channel="webhook", match=match, message=f"failed: {exc}")
