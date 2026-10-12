"""Tests for the FastAPI API layer (IntelX endpoint)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from leakwatch.api.app import create_app
from leakwatch.intelx import IntelXClient, IntelXError, IntelXInvalidSelectorError, IntelXResult
from leakwatch.pwned import PwnedPasswordsClient, PwnedPasswordsError


@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
async def client(app: Any) -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_search_invalid_short_selector_returns_422(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/intelx/search", params={"selector": "ab"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_missing_param_returns_422(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/intelx/search")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_no_key_returns_503(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeSettings:
        intelx_api_key = ""
        intelx_base_url = "https://x"
        api_cors_origins: list[str] = []

    monkeypatch.setattr("leakwatch.intelx.get_settings", _FakeSettings)
    resp = await client.get("/api/intelx/search", params={"selector": "alice@example.com"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_search_returns_results(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_search(self: IntelXClient, selector: str) -> list[IntelXResult]:
        return [
            IntelXResult(
                name="Acme Leak",
                bucket="leaks.public",
                bucket_human="Public Leaks",
                media_human="Paste",
                added="2024-05-01",
                description="db",
                xscore=88,
                preview="alice@example.com:hunter2",
                selector="alice@example.com",
                storage_id="abc",
            )
        ]

    monkeypatch.setattr(IntelXClient, "search", fake_search)

    resp = await client.get("/api/intelx/search", params={"selector": "alice@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["selector"] == "alice@example.com"
    assert len(body["results"]) == 1
    assert body["results"][0]["name"] == "Acme Leak"


@pytest.mark.asyncio
async def test_search_empty_results(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_search(self: IntelXClient, selector: str) -> list[IntelXResult]:
        return []

    monkeypatch.setattr(IntelXClient, "search", fake_search)

    resp = await client.get("/api/intelx/search", params={"selector": "clean@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"selector": "clean@example.com", "results": []}


@pytest.mark.asyncio
async def test_search_invalid_selector_returns_422(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_search(self: IntelXClient, selector: str) -> list[IntelXResult]:
        raise IntelXInvalidSelectorError("invalid")

    monkeypatch.setattr(IntelXClient, "search", fake_search)

    resp = await client.get("/api/intelx/search", params={"selector": "garbage"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_api_error_returns_502(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_search(self: IntelXClient, selector: str) -> list[IntelXResult]:
        raise IntelXError("boom")

    monkeypatch.setattr(IntelXClient, "search", fake_search)

    resp = await client.get("/api/intelx/search", params={"selector": "alice@example.com"})
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_api_has_cors_headers(client: httpx.AsyncClient) -> None:
    resp = await client.options(
        "/api/intelx/search",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --- Pwned Passwords endpoint ---


@pytest.mark.asyncio
async def test_pwned_check_breached_returns_count(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check_password(self: PwnedPasswordsClient, password: str) -> int:
        return 42

    monkeypatch.setattr(PwnedPasswordsClient, "check_password", fake_check_password)

    resp = await client.post("/api/pwned/check", json={"password": "password"})
    assert resp.status_code == 200
    assert resp.json() == {"count": 42, "breached": True}


@pytest.mark.asyncio
async def test_pwned_check_not_breached_returns_zero(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check_password(self: PwnedPasswordsClient, password: str) -> int:
        return 0

    monkeypatch.setattr(PwnedPasswordsClient, "check_password", fake_check_password)

    resp = await client.post("/api/pwned/check", json={"password": "cleanpass"})
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "breached": False}


@pytest.mark.asyncio
async def test_pwned_check_empty_password_returns_422(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/pwned/check", json={"password": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_pwned_check_api_error_returns_502(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check_password(self: PwnedPasswordsClient, password: str) -> int:
        raise PwnedPasswordsError("boom")

    monkeypatch.setattr(PwnedPasswordsClient, "check_password", fake_check_password)

    resp = await client.post("/api/pwned/check", json={"password": "password"})
    assert resp.status_code == 502


# --- Matches endpoint ---


@pytest.mark.asyncio
async def test_matches_endpoint_returns_matches(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_load_matches(session, limit):
        return [
            {
                "id": 1,
                "created_at": "2026-08-04T20:00:00",
                "domain": "example.com",
                "reason": "domain match",
                "credential": {"kind": "email", "value": "alice@example.com", "pair_id": "p1"},
                "paired_credential": {"kind": "password", "value": "hunter2", "pair_id": "p1"},
                "source": "pastebin",
                "url": "https://pastebin.com/abc12345",
                "fetched_at": "2026-08-04T19:00:00",
            }
        ]

    monkeypatch.setattr("leakwatch.api.matches.load_matches", fake_load_matches)

    resp = await client.get("/api/matches", params={"limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["matches"]) == 1
    m = body["matches"][0]
    assert m["credential"]["value"] == "alice@example.com"
    assert m["paired_credential"]["value"] == "hunter2"
    assert m["source"] == "pastebin"


@pytest.mark.asyncio
async def test_matches_endpoint_empty(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_matches(session, limit):
        return []

    monkeypatch.setattr("leakwatch.api.matches.load_matches", fake_load_matches)

    resp = await client.get("/api/matches")
    assert resp.status_code == 200
    assert resp.json() == {"matches": []}
