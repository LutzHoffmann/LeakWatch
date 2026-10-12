"""Tests for the Pastebin watcher."""

from __future__ import annotations

import httpx
import pytest

from leakwatch.schemas import RawItem
from leakwatch.watchers.pastebin import PastebinWatcher, parse_archive_ids


def _archive_html(paste_ids: list[str]) -> str:
    links = "".join(f'<a href="/{pid}">title {pid}</a>' for pid in paste_ids)
    # include some navigation links that must be filtered out
    return f"""
    <html><body>
      <a href="/archive">Archive</a>
      <a href="/trends">Trends</a>
      {links}
      <a href="/print/abc">Print</a>
    </body></html>
    """


def test_parse_archive_ids_extracts_only_paste_ids() -> None:
    html = _archive_html(["abc12345", "Zx9kM2pQ", "111aaaaa"])
    ids = parse_archive_ids(html)
    assert ids == ["abc12345", "Zx9kM2pQ", "111aaaaa"]


def test_parse_archive_ids_dedupes() -> None:
    html = _archive_html(["abc12345", "abc12345"])
    assert parse_archive_ids(html) == ["abc12345"]


def test_parse_archive_ids_ignores_short_and_long_links() -> None:
    html = '<a href="/abc">x</a><a href="/abcdefghi">y</a><a href="/abc12345">z</a>'
    assert parse_archive_ids(html) == ["abc12345"]


def test_parse_archive_ids_empty_on_no_matches() -> None:
    assert parse_archive_ids("<html><body>no links</body></html>") == []


@pytest.mark.asyncio
async def test_pastebin_watcher_polls_and_fetches_raw() -> None:
    paste_ids = ["abc12345", "Zx9kM2pQ"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive":
            return httpx.Response(200, text=_archive_html(paste_ids))
        if request.url.path.startswith("/raw/"):
            pid = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, text=f"raw content of {pid}")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = PastebinWatcher(client=client, max_pastes=10, fetch_delay=0.0)

    items = await watcher.poll()

    assert len(items) == 2
    assert all(isinstance(i, RawItem) for i in items)
    assert {i.external_id for i in items} == set(paste_ids)
    assert items[0].source == "pastebin"
    assert items[0].content == "raw content of abc12345"
    assert items[0].url == "https://pastebin.com/abc12345"
    await client.aclose()


@pytest.mark.asyncio
async def test_pastebin_watcher_respects_max_pastes() -> None:
    paste_ids = [f"abc0000{i}" for i in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive":
            return httpx.Response(200, text=_archive_html(paste_ids))
        return httpx.Response(200, text="x")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = PastebinWatcher(client=client, max_pastes=2, fetch_delay=0.0)

    items = await watcher.poll()
    assert len(items) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_pastebin_watcher_returns_empty_on_archive_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(403))
    client = httpx.AsyncClient(transport=transport)
    watcher = PastebinWatcher(client=client, fetch_delay=0.0)

    assert await watcher.poll() == []
    await client.aclose()


@pytest.mark.asyncio
async def test_pastebin_watcher_records_empty_content_on_raw_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive":
            return httpx.Response(200, text=_archive_html(["abc12345"]))
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    watcher = PastebinWatcher(client=client, fetch_delay=0.0)

    items = await watcher.poll()
    assert len(items) == 1
    assert items[0].content == ""
    await client.aclose()


def test_pastebin_watcher_sends_browser_headers() -> None:
    watcher = PastebinWatcher(fetch_delay=0.0)
    headers = watcher._headers()
    assert "Mozilla" in headers["User-Agent"]
    assert "text/html" in headers["Accept"]
