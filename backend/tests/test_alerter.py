"""Tests for the Alerter."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from leakwatch.alerter import Alerter
from leakwatch.schemas import Credential, CredentialKind, Match


def _match() -> Match:
    return Match(
        credential=Credential(kind=CredentialKind.EMAIL, value="alice@example.com"),
        domain_value="example.com",
        reason="email domain matches example.com",
    )


def _settings(**overrides: Any) -> Any:
    base = dict(
        resend_api_key="",
        alert_from_email="from@x.test",
        alert_to_email="",
        telegram_bot_token="",
        telegram_chat_id="",
        alert_webhook_url="",
    )
    base.update(overrides)

    class _S:
        def __init__(self, d: dict[str, Any]) -> None:
            for k, v in d.items():
                setattr(self, k, v)

        @property
        def email_enabled(self) -> bool:
            return bool(self.resend_api_key and self.alert_to_email)

        @property
        def telegram_enabled(self) -> bool:
            return bool(self.telegram_bot_token and self.telegram_chat_id)

        @property
        def webhook_enabled(self) -> bool:
            return bool(self.alert_webhook_url)

    return _S(base)


@pytest.mark.asyncio
async def test_no_channel_enabled_returns_empty() -> None:
    alerter = Alerter(settings=_settings(), client=httpx.AsyncClient())
    result = await alerter.send(_match())
    assert result == []


@pytest.mark.asyncio
async def test_telegram_alert_sent() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Response(200, json={}).json
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    settings = _settings(telegram_bot_token="tok", telegram_chat_id="123")
    alerter = Alerter(settings=settings, client=httpx.AsyncClient(transport=transport))
    result = await alerter.send(_match())
    assert len(result) == 1
    assert result[0].channel == "telegram"
    assert "/bot123/sendMessage" in captured["url"] or "tok" in captured["url"]


@pytest.mark.asyncio
async def test_telegram_alert_failure_recorded() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    settings = _settings(telegram_bot_token="tok", telegram_chat_id="123")
    alerter = Alerter(settings=settings, client=httpx.AsyncClient(transport=transport))
    result = await alerter.send(_match())
    assert result[0].channel == "telegram"
    assert result[0].message.startswith("failed")


@pytest.mark.asyncio
async def test_webhook_alert_sent() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    settings = _settings(alert_webhook_url="https://hook.test/n")
    alerter = Alerter(settings=settings, client=httpx.AsyncClient(transport=transport))
    result = await alerter.send(_match())
    assert result[0].channel == "webhook"
    assert "message" in captured["json"]


@pytest.mark.asyncio
async def test_webhook_alert_failure_recorded() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    settings = _settings(alert_webhook_url="https://hook.test/n")
    alerter = Alerter(settings=settings, client=httpx.AsyncClient(transport=transport))
    result = await alerter.send(_match())
    assert result[0].message.startswith("failed")


@pytest.mark.asyncio
async def test_email_alert_uses_resend(monkeypatch: pytest.MonkeyPatch) -> None:

    sent: dict[str, Any] = {}

    class FakeEmails:
        def send(self, params: dict[str, Any]) -> Any:
            sent["params"] = params
            return {"id": "r1"}

    fake_resend = SimpleNamespace(api_key=None, Emails=FakeEmails())
    monkeypatch.setitem(sys.modules, "resend", fake_resend)

    settings = _settings(resend_api_key="re_", alert_to_email="to@x.test")
    al = Alerter(settings=settings, client=httpx.AsyncClient())
    result = await al.send(_match())
    assert result[0].channel == "email"
    assert sent["params"]["to"] == ["to@x.test"]


@pytest.mark.asyncio
async def test_email_alert_failure_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEmails:
        def send(self, params: dict[str, Any]) -> Any:
            raise RuntimeError("boom")

    fake_resend = SimpleNamespace(api_key=None, Emails=FakeEmails())
    monkeypatch.setitem(sys.modules, "resend", fake_resend)

    settings = _settings(resend_api_key="re_", alert_to_email="to@x.test")
    al = Alerter(settings=settings, client=httpx.AsyncClient())
    result = await al.send(_match())
    assert result[0].channel == "email"
    assert "failed" in result[0].message


def test_format_message() -> None:
    al = Alerter(settings=_settings(), client=httpx.AsyncClient())
    msg = al._format_message(_match())
    assert "alice@example.com" in msg
    assert "example.com" in msg
