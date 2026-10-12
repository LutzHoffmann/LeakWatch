"""Tests for the ARQ worker core loop (integration with SQLite)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from leakwatch import models, worker
from leakwatch.persistence import get_or_create_user_domain
from leakwatch.schemas import AlertPayload, Credential, CredentialKind, RawItem


class _FakeWatcher:
    """Watcher emitting a single raw item containing a monitored email."""

    name = "fake"

    def __init__(self, content: str = "alice@example.com") -> None:
        self._content = content

    async def poll(self) -> list[RawItem]:
        return [
            RawItem(
                source="fake",
                external_id="1",
                url="https://x.test/1",
                content=self._content,
            )
        ]


class _FailingWatcher:
    name = "boom"

    async def poll(self) -> list[RawItem]:
        raise RuntimeError("source down")


class _StubAnalyzer:
    """Analyzer returning a fixed list of credentials."""

    def __init__(self, creds: list[Credential]) -> None:
        self._creds = creds

    async def extract_credentials(self, text: str) -> list[Credential]:
        return list(self._creds)


class _StubAlerter:
    """Alerter recording payloads and returning one per channel."""

    def __init__(self, channels: list[str] | None = None) -> None:
        self._channels = channels if channels is not None else ["telegram"]
        self.sent: list[Any] = []

    async def send(self, match: Any) -> list[Any]:
        payloads = [AlertPayload(channel=ch, match=match, message=f"alert via {ch}") for ch in self._channels]
        self.sent.extend(payloads)
        return payloads


def _patch_worker(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: Any,
    watchers: list[Any],
    analyzer: Any,
    alerter: Any,
) -> None:
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(worker, "build_watchers", lambda: watchers)
    monkeypatch.setattr(worker, "OpenRouterClient", lambda *a, **k: None)
    monkeypatch.setattr(worker, "LeakAnalyzer", lambda llm=None: analyzer)
    monkeypatch.setattr(worker, "Alerter", lambda settings=None: alerter)


@pytest.mark.asyncio
async def test_run_watch_cycle_persists_full_chain(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_session_factory: Any,
    sqlite_session: Any,
) -> None:
    # seed a monitored domain so matching can succeed
    await get_or_create_user_domain(sqlite_session, "example.com")
    await sqlite_session.commit()

    cred = Credential(kind=CredentialKind.EMAIL, value="alice@example.com")
    analyzer = _StubAnalyzer([cred])
    alerter = _StubAlerter(channels=["telegram"])
    _patch_worker(
        monkeypatch, sqlite_session_factory, [_FakeWatcher()], analyzer, alerter
    )

    stats = await worker.run_watch_cycle({})

    assert stats == {"raw_items": 1, "credentials": 1, "matches": 1, "alerts": 1}

    raw_rows = (await sqlite_session.execute(select(models.RawItem))).scalars().all()
    cred_rows = (await sqlite_session.execute(select(models.Credential))).scalars().all()
    match_rows = (await sqlite_session.execute(select(models.Match))).scalars().all()
    alert_rows = (await sqlite_session.execute(select(models.Alert))).scalars().all()

    assert len(raw_rows) == 1
    assert raw_rows[0].source == "fake"
    assert len(cred_rows) == 1
    assert cred_rows[0].kind == "email"
    assert cred_rows[0].value == "alice@example.com"
    assert len(match_rows) == 1
    assert len(alert_rows) == 1
    assert alert_rows[0].channel == "telegram"
    assert alert_rows[0].status == "sent"


@pytest.mark.asyncio
async def test_run_watch_cycle_seeds_defaults_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_session_factory: Any,
    sqlite_session: Any,
) -> None:
    cred = Credential(kind=CredentialKind.EMAIL, value="alice@example.com")
    analyzer = _StubAnalyzer([cred])
    alerter = _StubAlerter(channels=[])
    _patch_worker(
        monkeypatch, sqlite_session_factory, [_FakeWatcher()], analyzer, alerter
    )

    stats = await worker.run_watch_cycle({})

    # default domain example.com seeded -> match happens
    assert stats["matches"] == 1
    domains = (await sqlite_session.execute(select(models.UserDomain))).scalars().all()
    assert any(d.value == "example.com" for d in domains)


@pytest.mark.asyncio
async def test_run_watch_cycle_dedups_raw_items_across_cycles(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_session_factory: Any,
    sqlite_session: Any,
) -> None:
    await get_or_create_user_domain(sqlite_session, "example.com")
    await sqlite_session.commit()

    analyzer = _StubAnalyzer([Credential(kind=CredentialKind.EMAIL, value="alice@example.com")])
    alerter = _StubAlerter(channels=[])
    _patch_worker(
        monkeypatch, sqlite_session_factory, [_FakeWatcher()], analyzer, alerter
    )

    await worker.run_watch_cycle({})
    second = await worker.run_watch_cycle({})

    # second cycle sees the same external_id -> deduped, no new raw items
    assert second == {"raw_items": 0, "credentials": 0, "matches": 0, "alerts": 0}
    raw_rows = (await sqlite_session.execute(select(models.RawItem))).scalars().all()
    assert len(raw_rows) == 1


@pytest.mark.asyncio
async def test_run_watch_cycle_handles_watcher_failure(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_session_factory: Any,
) -> None:
    analyzer = _StubAnalyzer([])
    alerter = _StubAlerter(channels=[])
    _patch_worker(
        monkeypatch, sqlite_session_factory, [_FailingWatcher()], analyzer, alerter
    )

    stats = await worker.run_watch_cycle({})
    assert stats == {"raw_items": 0, "credentials": 0, "matches": 0, "alerts": 0}


@pytest.mark.asyncio
async def test_run_watch_cycle_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_session_factory: Any,
    sqlite_session: Any,
) -> None:
    await get_or_create_user_domain(sqlite_session, "example.com")
    await sqlite_session.commit()

    analyzer = _StubAnalyzer([])
    alerter = _StubAlerter(channels=[])
    _patch_worker(
        monkeypatch, sqlite_session_factory, [_FakeWatcher()], analyzer, alerter
    )

    stats = await worker.run_watch_cycle({})
    assert stats["raw_items"] == 1
    assert stats["credentials"] == 0
    assert stats["matches"] == 0


@pytest.mark.asyncio
async def test_run_watch_cycle_records_failed_alert_status(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_session_factory: Any,
    sqlite_session: Any,
) -> None:
    await get_or_create_user_domain(sqlite_session, "example.com")
    await sqlite_session.commit()

    analyzer = _StubAnalyzer([Credential(kind=CredentialKind.EMAIL, value="alice@example.com")])
    alerter = _StubAlerter(channels=["webhook"])
    alerter.send_returns_failed = True
    _patch_worker(
        monkeypatch, sqlite_session_factory, [_FakeWatcher()], analyzer, alerter
    )

    # patch the stub to return a "failed" message
    original_send = alerter.send

    async def failing_send(match: Any) -> list[Any]:
        return [AlertPayload(channel="webhook", match=match, message="failed: webhook down")]

    alerter.send = failing_send  # type: ignore[assignment]

    await worker.run_watch_cycle({})
    alert_rows = (await sqlite_session.execute(select(models.Alert))).scalars().all()
    assert len(alert_rows) == 1
    assert alert_rows[0].status == "failed"
    _ = original_send


def test_worker_settings_has_cron() -> None:
    assert worker.WorkerSettings.cron_jobs
    assert worker.WorkerSettings.cron_jobs[0]["func"] is worker.run_watch_cycle
