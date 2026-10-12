"""Tests for the watcher layer."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from leakwatch.schemas import RawItem
from leakwatch.watchers import GitHubGistWatcher
from leakwatch.watchers.base import BaseWatcher


class _RecordingWatcher(BaseWatcher):
    name = "recording"

    def __init__(self) -> None:
        self.calls = 0

    async def poll(self) -> list[RawItem]:
        self.calls += 1
        return [self.make_raw_item(self.name, "id-1", "https://example.test/1", "hello")]


def test_base_watcher_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseWatcher()  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_base_watcher_make_raw_item() -> None:
    item = _RecordingWatcher.make_raw_item("src", "ext", "https://x", "content")
    assert item.source == "src"
    assert item.external_id == "ext"
    assert item.content == "content"


@pytest.mark.asyncio
async def test_recording_watcher_polls() -> None:
    watcher = _RecordingWatcher()
    items = await watcher.poll()
    assert len(items) == 1
    assert items[0].source == "recording"
    assert watcher.calls == 1


def _gist_list_response() -> list[dict[str, Any]]:
    return [
        {
            "id": "gist-1",
            "html_url": "https://gist.github.com/gist-1",
        },
        {
            "id": "gist-2",
            "html_url": "https://gist.github.com/gist-2",
        },
    ]


def _gist_detail_response(gist_id: str) -> dict[str, Any]:
    return {
        "id": gist_id,
        "files": {
            "a.txt": {"content": f"content of {gist_id}"},
            "b.txt": {"content": "second file"},
        },
    }


@pytest.mark.asyncio
async def test_github_gist_watcher_polls_and_fetches_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gists/public":
            return httpx.Response(200, json=_gist_list_response())
        if request.url.path.startswith("/gists/"):
            gist_id = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json=_gist_detail_response(gist_id))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubGistWatcher(token="tok", client=client, per_page=10)

    items = await watcher.poll()

    assert len(items) == 2
    assert all(isinstance(i, RawItem) for i in items)
    assert {i.external_id for i in items} == {"gist-1", "gist-2"}
    assert "content of gist-1" in items[0].content
    assert items[0].source == "github_gist"
    await client.aclose()


@pytest.mark.asyncio
async def test_github_gist_watcher_skips_content_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gists/public":
            return httpx.Response(200, json=_gist_list_response())
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = GitHubGistWatcher(token="tok", client=client)

    items = await watcher.poll()
    assert len(items) == 2
    assert all(i.content == "" for i in items)
    await client.aclose()


def test_github_gist_watcher_requires_token_for_headers() -> None:
    watcher = GitHubGistWatcher(token="abc")
    headers = watcher._headers()
    assert headers["Authorization"] == "Bearer abc"
