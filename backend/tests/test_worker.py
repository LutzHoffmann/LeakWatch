"""Tests for the ARQ worker core loop."""

from __future__ import annotations

from typing import Any

import pytest

from leakwatch import worker
from leakwatch.schemas import Credential, CredentialKind, RawItem


class _FakeWatcher:
    name = "fake"

    async def poll(self) -> list[RawItem]:
        return [
            RawItem(
                source="fake",
                external_id="1",
                url="https://x.test/1",
                content="alice@example.com",
            )
        ]


class _FailingWatcher:
    name = "boom"

    async def poll(self) -> list[RawItem]:
        raise RuntimeError("source down")


class _StubAnalyzer:
    def __init__(self, creds: list[Credential]) -> None:
        self._creds = creds

    async def extract_credentials(self, text: str) -> list[Credential]:
        return list(self._creds)


class _StubMatcher:
    async def check(self, creds: list[Credential]) -> list[dict[str, Any]]:
        return [{"credential": c, "domain_value": "example.com", "reason": "x"} for c in creds]


class _StubAlerter:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    async def send(self, match: Any) -> list[Any]:
        self.sent.append(match)
        return [match]


@pytest.mark.asyncio
async def test_run_watch_cycle_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    cred = Credential(kind=CredentialKind.EMAIL, value="alice@example.com")
    analyzer = _StubAnalyzer([cred])
    matcher = _StubMatcher()
    alerter = _StubAlerter()

    monkeypatch.setattr(worker, "build_watchers", lambda: [_FakeWatcher()])
    monkeypatch.setattr(worker, "OpenRouterClient", lambda *a, **k: None)
    monkeypatch.setattr(worker, "LeakAnalyzer", lambda llm=None: analyzer)
    monkeypatch.setattr(worker, "DomainMatcher", lambda source: matcher)
    monkeypatch.setattr(worker, "StaticDomainSource", lambda domains: None)
    monkeypatch.setattr(worker, "Alerter", lambda settings=None: alerter)

    stats = await worker.run_watch_cycle({})

    assert stats == {"raw_items": 1, "credentials": 1, "matches": 1, "alerts": 1}
    assert len(alerter.sent) == 1


@pytest.mark.asyncio
async def test_run_watch_cycle_handles_watcher_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = _StubAnalyzer([])
    matcher = _StubMatcher()
    alerter = _StubAlerter()

    monkeypatch.setattr(worker, "build_watchers", lambda: [_FailingWatcher()])
    monkeypatch.setattr(worker, "OpenRouterClient", lambda *a, **k: None)
    monkeypatch.setattr(worker, "LeakAnalyzer", lambda llm=None: analyzer)
    monkeypatch.setattr(worker, "DomainMatcher", lambda source: matcher)
    monkeypatch.setattr(worker, "StaticDomainSource", lambda domains: None)
    monkeypatch.setattr(worker, "Alerter", lambda settings=None: alerter)

    stats = await worker.run_watch_cycle({})
    assert stats == {"raw_items": 0, "credentials": 0, "matches": 0, "alerts": 0}


@pytest.mark.asyncio
async def test_run_watch_cycle_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = _StubAnalyzer([])
    matcher = _StubMatcher()
    alerter = _StubAlerter()

    monkeypatch.setattr(worker, "build_watchers", lambda: [_FakeWatcher()])
    monkeypatch.setattr(worker, "OpenRouterClient", lambda *a, **k: None)
    monkeypatch.setattr(worker, "LeakAnalyzer", lambda llm=None: analyzer)
    monkeypatch.setattr(worker, "DomainMatcher", lambda source: matcher)
    monkeypatch.setattr(worker, "StaticDomainSource", lambda domains: None)
    monkeypatch.setattr(worker, "Alerter", lambda settings=None: alerter)

    stats = await worker.run_watch_cycle({})
    assert stats["raw_items"] == 1
    assert stats["credentials"] == 0
    assert stats["matches"] == 0


def test_worker_settings_has_cron() -> None:
    assert worker.WorkerSettings.cron_jobs
    assert worker.WorkerSettings.cron_jobs[0]["func"] is worker.run_watch_cycle
