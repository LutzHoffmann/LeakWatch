"""Tests for the Intelligence X client."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from leakwatch.intelx import (
    IntelXClient,
    IntelXError,
    IntelXInvalidSelectorError,
    IntelXNotConfiguredError,
    IntelXResult,
)


def _records() -> list[dict[str, Any]]:
    return [
        {
            "name": "Acme Leak 2024",
            "bucket": "leaks.public",
            "bucketh": "Public Leaks",
            "mediah": "Paste",
            "added": "2024-05-01 12:00:00",
            "description": "A leaked database.",
            "xscore": 88,
            "preview": "alice@example.com:hunter2",
            "selector": "alice@example.com",
            "storageid": "abc123",
        }
    ]


def _handler_factory(start_id: str = "search-1", records: list[dict[str, Any]] | None = None):
    """Return a MockTransport handler implementing the IntelX async-search flow."""
    records = records if records is not None else _records()
    started = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/intelligent/search" and request.method == "POST":
            started["n"] += 1
            assert request.headers["X-Key"] == "k"
            return httpx.Response(200, json={"id": start_id, "status": 0, "softselectorwarning": False})
        if request.url.path == "/intelligent/search/result" and request.method == "GET":
            # First poll returns records + status 1 (no more), subsequent polls empty.
            if started["n"] == 1:
                started["n"] += 1
                return httpx.Response(200, json={"records": records, "status": 1})
            return httpx.Response(200, json={"records": [], "status": 1})
        if request.url.path == "/intelligent/search/terminate" and request.method == "GET":
            return httpx.Response(200, json={"status": 0})
        return httpx.Response(404)

    return handler


@pytest.mark.asyncio
async def test_intelx_search_returns_results() -> None:
    transport = httpx.MockTransport(_handler_factory())
    client = httpx.AsyncClient(transport=transport)
    intelx = IntelXClient(api_key="k", client=client, max_results=10, poll_interval=0)

    results = await intelx.search("alice@example.com")

    assert len(results) == 1
    assert isinstance(results[0], IntelXResult)
    assert results[0].name == "Acme Leak 2024"
    assert results[0].bucket_human == "Public Leaks"
    assert results[0].xscore == 88
    assert "hunter2" in results[0].preview
    await client.aclose()


@pytest.mark.asyncio
async def test_intelx_search_no_key_raises_not_configured() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport)
    intelx = IntelXClient(api_key="", client=client)

    with pytest.raises(IntelXNotConfiguredError):
        await intelx.search("alice@example.com")
    await client.aclose()


@pytest.mark.asyncio
async def test_intelx_search_invalid_selector_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "", "status": 1})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    intelx = IntelXClient(api_key="k", client=client)

    with pytest.raises(IntelXInvalidSelectorError):
        await intelx.search("garbage")
    await client.aclose()


@pytest.mark.asyncio
async def test_intelx_search_unauthorized_raises() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(401, text="nope"))
    client = httpx.AsyncClient(transport=transport)
    intelx = IntelXClient(api_key="bad", client=client)

    with pytest.raises(IntelXError, match="unauthorized"):
        await intelx.search("alice@example.com")
    await client.aclose()


@pytest.mark.asyncio
async def test_intelx_search_payment_required_raises() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(402, text="pay"))
    client = httpx.AsyncClient(transport=transport)
    intelx = IntelXClient(api_key="k", client=client)

    with pytest.raises(IntelXError, match="payment required"):
        await intelx.search("alice@example.com")
    await client.aclose()


@pytest.mark.asyncio
async def test_intelx_search_terminates_on_result_error() -> None:
    terminated = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/intelligent/search" and request.method == "POST":
            return httpx.Response(200, json={"id": "sid", "status": 0})
        if request.url.path == "/intelligent/search/result":
            return httpx.Response(500, text="boom")
        if request.url.path == "/intelligent/search/terminate":
            terminated["n"] += 1
            return httpx.Response(200, json={"status": 0})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    intelx = IntelXClient(api_key="k", client=client, poll_interval=0)

    with pytest.raises(IntelXError):
        await intelx.search("alice@example.com")
    assert terminated["n"] == 1
    await client.aclose()


def test_intelx_result_to_dict_roundtrip() -> None:
    r = IntelXResult.from_api(_records()[0])
    d = r.to_dict()
    assert d["name"] == "Acme Leak 2024"
    assert d["bucket"] == "leaks.public"
    assert d["xscore"] == 88
    assert d["storage_id"] == "abc123"
