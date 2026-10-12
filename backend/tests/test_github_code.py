"""Tests for the GitHub Code Search watcher."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from leakwatch.schemas import RawItem
from leakwatch.watchers import GitHubCodeSearchWatcher


def _code_search_response() -> dict[str, Any]:
    return {
        "total_count": 2,
        "items": [
            {
                "id": 101,
                "sha": "abc123",
                "path": "config/secrets.yaml",
                "html_url": "https://github.com/acme/app/blob/abc123/config/secrets.yaml",
                "repository": {"full_name": "acme/app"},
                "text_matches": [
                    {"fragment": "password: hunter2"},
                    {"fragment": "api_key: sk-1234"},
                ],
            },
            {
                "id": 102,
                "sha": "def456",
                "path": "id_rsa",
                "html_url": "https://github.com/acme/app/blob/def456/id_rsa",
                "repository": {"full_name": "acme/app"},
                "text_matches": [
                    {"fragment": "-----BEGIN RSA PRIVATE KEY-----"},
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_github_code_search_polls_and_builds_raw_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search/code"
        assert request.headers["Authorization"] == "Bearer tok"
        assert "q=password" in str(request.url)
        return httpx.Response(200, json=_code_search_response())

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubCodeSearchWatcher(
        token="tok", client=client, queries=["password"], max_results=10
    )

    items = await watcher.poll()

    assert len(items) == 2
    assert all(isinstance(i, RawItem) for i in items)
    assert {i.external_id for i in items} == {"abc123", "def456"}
    assert items[0].source == "github_code"
    assert "hunter2" in items[0].content
    assert "acme/app/config/secrets.yaml" in items[0].content
    await client.aclose()


@pytest.mark.asyncio
async def test_github_code_search_skips_when_no_token() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"items": []}))
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubCodeSearchWatcher(token="", client=client, queries=["password"])

    items = await watcher.poll()

    assert items == []
    await client.aclose()


@pytest.mark.asyncio
async def test_github_code_search_dedups_across_queries() -> None:
    # Both queries return the same result -> only one RawItem emitted.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_code_search_response())

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubCodeSearchWatcher(
        token="tok", client=client, queries=["password", "api_key"], max_results=10
    )

    items = await watcher.poll()

    assert len(items) == 2  # deduped by html_url
    await client.aclose()


@pytest.mark.asyncio
async def test_github_code_search_continues_on_query_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=_code_search_response())

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubCodeSearchWatcher(
        token="tok", client=client, queries=["bad", "good"], max_results=10
    )

    items = await watcher.poll()

    assert len(items) == 2  # only the second (good) query produced results
    await client.aclose()


@pytest.mark.asyncio
async def test_github_code_search_respects_max_results() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=_code_search_response()))
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubCodeSearchWatcher(
        token="tok", client=client, queries=["password"], max_results=1
    )

    items = await watcher.poll()

    assert len(items) == 1
    await client.aclose()
