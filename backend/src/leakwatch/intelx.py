"""Intelligence X (IntelX) client — selector search across leaks, pastes and darknet sources.

IntelX aggregates paste sites, leaked databases, darknet content and public
records behind a single search API. A "selector" is a strong search term such
as an email address, domain, URL, IP, phone number or crypto address.

The search is asynchronous: ``POST /intelligent/search`` starts a search job
and returns an id, then ``GET /intelligent/search/result?id=...`` is polled
until the job reports no more results. The client polls until a result count
is reached or a timeout elapses, then terminates the search job.

API access requires an IntelX subscription (Professional/Enterprise). Without
a key the client raises ``IntelXNotConfiguredError`` so the API layer can
return a clean 503.

Reference: https://github.com/IntelligenceX/SDK
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from .config import get_settings

log = structlog.get_logger(__name__)

INTELX_DEFAULT_BASE_URL = "https://2.intelx.io"

# Sort orders (see IntelX SDK API.go).
SORT_XSCORE_DESC = 2


@dataclass(frozen=True)
class IntelXResult:
    """A single search result record returned by IntelX."""

    name: str
    bucket: str
    bucket_human: str
    media_human: str
    added: str
    description: str
    xscore: int
    preview: str
    selector: str
    storage_id: str

    @classmethod
    def from_api(cls, r: dict[str, Any]) -> IntelXResult:
        return cls(
            name=str(r.get("name", "")),
            bucket=str(r.get("bucket", "")),
            bucket_human=str(r.get("bucketh", "")),
            media_human=str(r.get("mediah", "")),
            added=str(r.get("added", "")),
            description=str(r.get("description", "")),
            xscore=int(r.get("xscore", 0) or 0),
            preview=str(r.get("preview", "")),
            selector=str(r.get("selector", "")),
            storage_id=str(r.get("storageid", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bucket": self.bucket,
            "bucket_human": self.bucket_human,
            "media_human": self.media_human,
            "added": self.added,
            "description": self.description,
            "xscore": self.xscore,
            "preview": self.preview,
            "selector": self.selector,
            "storage_id": self.storage_id,
        }


class IntelXError(Exception):
    """Raised when the IntelX API call fails unexpectedly."""


class IntelXNotConfiguredError(IntelXError):
    """Raised when no IntelX API key is configured."""


class IntelXInvalidSelectorError(IntelXError):
    """Raised when IntelX rejects the selector as invalid."""


class IntelXClient:
    """Async client for the Intelligence X search API."""

    def __init__(  # noqa: PLR0913
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        *,
        max_results: int = 100,
        poll_interval: float = 0.25,
        timeout: float = 20.0,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.intelx_api_key
        self._base_url = (base_url if base_url is not None else settings.intelx_base_url).rstrip("/")
        self._client = client
        self._max_results = max_results
        self._poll_interval = poll_interval
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"X-Key": self._api_key, "User-Agent": "LeakWatch", "Content-Type": "application/json"}

    async def _start_search(self, selector: str) -> str:
        client = await self._get_client()
        body = {
            "term": selector,
            "buckets": [],
            "timeout": 0,
            "maxresults": self._max_results,
            "datefrom": "",
            "dateto": "",
            "sort": SORT_XSCORE_DESC,
            "media": 0,
            "terminate": [],
        }
        resp = await client.post(f"{self._base_url}/intelligent/search", json=body, headers=self._headers())
        if resp.status_code == 401:
            raise IntelXError("IntelX unauthorized — check INTELX_API_KEY")
        if resp.status_code == 402:
            raise IntelXError("IntelX payment required — API access needs a paid subscription")
        if resp.status_code >= 400:
            raise IntelXError(f"IntelX search start failed: {resp.status_code} {resp.text}")
        data = resp.json()
        status = int(data.get("status", 0))
        if status == 1:
            raise IntelXInvalidSelectorError("IntelX rejected the selector as invalid")
        if status == 2:
            raise IntelXError("IntelX max concurrent searches reached")
        search_id = str(data.get("id", ""))
        if not search_id:
            raise IntelXError("IntelX returned no search id")
        return search_id

    async def _get_results(self, search_id: str, limit: int) -> tuple[list[IntelXResult], int]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/intelligent/search/result",
            params={"id": search_id, "limit": limit, "previewlines": 20},
            headers=self._headers(),
        )
        if resp.status_code >= 400:
            raise IntelXError(f"IntelX result fetch failed: {resp.status_code} {resp.text}")
        data = resp.json()
        status = int(data.get("status", 0))
        records: list[dict[str, Any]] = data.get("records", [])
        return [IntelXResult.from_api(r) for r in records], status

    async def _terminate(self, search_id: str) -> None:
        client = await self._get_client()
        try:
            await client.get(
                f"{self._base_url}/intelligent/search/terminate",
                params={"id": search_id},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            log.debug("intelx_terminate_failed", error=str(exc))

    async def search(self, selector: str) -> list[IntelXResult]:
        """Search IntelX for ``selector`` (email, domain, IP, ...) and return results."""
        if not self._api_key:
            raise IntelXNotConfiguredError("INTELX_API_KEY is not configured")
        search_id = await self._start_search(selector)
        # Brief wait so IntelX can sort, then poll until done or timeout.
        await asyncio.sleep(0.4)
        results: list[IntelXResult] = []
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = self._max_results - len(results)
            if remaining <= 0:
                break
            try:
                records, status = await self._get_results(search_id, remaining)
            except IntelXError:
                await self._terminate(search_id)
                raise
            if records:
                results.extend(records)
            # status: 0 = more available, 1 = no more, 2 = id not found, 3 = keep trying, 4 = error
            if status not in (0, 3):
                break
            if len(results) >= self._max_results or time.monotonic() >= deadline:
                break
            await asyncio.sleep(self._poll_interval)
        await self._terminate(search_id)
        return results[: self._max_results]
