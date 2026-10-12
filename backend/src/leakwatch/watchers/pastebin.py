"""Pastebin watcher.

Scrapes Pastebin's public archive (`https://pastebin.com/archive`) for newly
posted pastes, then fetches each paste's raw body from
`https://pastebin.com/raw/<id>` and emits :class:`RawItem` instances.

Pastebin aggressively rate-limits and blocks non-browser traffic, so the
watcher:

* sends a realistic ``User-Agent`` header,
* caps the number of pastes inspected per poll via ``max_pastes``,
* optionally sleeps between raw fetches via ``fetch_delay`` (default 0.5s) to
  avoid hammering the endpoint.

Both ``max_pastes`` and ``fetch_delay`` are injectable for tests.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from ..schemas import RawItem
from .base import BaseWatcher

log = structlog.get_logger(__name__)

PASTEBIN_ARCHIVE_URL = "https://pastebin.com/archive"
PASTEBIN_RAW_URL = "https://pastebin.com/raw/{paste_id}"

# Pastebin paste ids are 8-char alphanumeric tokens, e.g. "abc12345".
_PASTE_ID_RE = re.compile(r"^/[A-Za-z0-9]{8}$")

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class PastebinWatcher(BaseWatcher):
    name = "pastebin"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        max_pastes: int = 20,
        fetch_delay: float = 0.5,
    ) -> None:
        self._client = client
        self._max_pastes = max_pastes
        self._fetch_delay = fetch_delay

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": _BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def _fetch_archive(self) -> list[str]:
        """Return the paste ids listed on the public archive page (deduped, order-preserving)."""
        client = await self._get_client()
        resp = await client.get(PASTEBIN_ARCHIVE_URL, headers=self._headers())
        resp.raise_for_status()
        return parse_archive_ids(resp.text)

    async def _fetch_raw(self, paste_id: str) -> str:
        client = await self._get_client()
        resp = await client.get(
            PASTEBIN_RAW_URL.format(paste_id=paste_id),
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.text

    async def poll(self) -> list[RawItem]:
        try:
            paste_ids = await self._fetch_archive()
        except httpx.HTTPError as exc:
            log.warning("pastebin_archive_fetch_failed", error=str(exc))
            return []

        items: list[RawItem] = []
        for paste_id in paste_ids[: self._max_pastes]:
            url = f"https://pastebin.com/{paste_id}"
            try:
                content = await self._fetch_raw(paste_id)
            except httpx.HTTPError as exc:
                log.warning("pastebin_raw_fetch_failed", paste_id=paste_id, error=str(exc))
                content = ""
            items.append(self.make_raw_item(self.name, paste_id, url, content))
            if self._fetch_delay > 0:
                await asyncio.sleep(self._fetch_delay)
        return items


def parse_archive_ids(html: str) -> list[str]:
    """Extract paste ids from the Pastebin archive HTML.

    The archive lists pastes as ``<a href="/XXXXXXXX" ...>`` links. We match
    only 8-char alphanumeric hrefs to avoid navigation links like ``/archive``,
    ``/trends`` or ``/print``.
    """
    soup: Any = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    ids: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if _PASTE_ID_RE.match(href):
            paste_id = href[1:]
            if paste_id not in seen:
                seen.add(paste_id)
                ids.append(paste_id)
    return ids
