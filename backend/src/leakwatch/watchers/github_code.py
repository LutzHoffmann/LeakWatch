"""GitHub Code Search watcher.

Polls the GitHub Code Search API (`GET /search/code`) for a configurable set
of queries — e.g. leaked passwords, API keys, private keys — and emits one
:class:`RawItem` per matching code result. The matched code fragment (returned
via the `text-match` media type) becomes the raw item content, so downstream
GLM analysis can extract credentials from it.

Authentication is **required** by the Code Search API, so this watcher is a
no-op when no GitHub token is configured.

Reference: https://docs.github.com/rest/search/search#search-code
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from ..config import get_settings
from ..schemas import RawItem
from .base import BaseWatcher

GITHUB_API = "https://api.github.com"

# Text-match media type makes GitHub include `text_matches[].fragment` in each
# result, which is the snippet surrounding the query hit.
ACCEPT_TEXT_MATCH = "application/vnd.github.v3.text-match+json"

log = structlog.get_logger(__name__)


class GitHubCodeSearchWatcher(BaseWatcher):
    name = "github_code"

    def __init__(
        self,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
        queries: list[str] | None = None,
        max_results: int | None = None,
    ) -> None:
        self._settings = get_settings()
        self._token = token if token is not None else self._settings.github_token
        self._client = client
        self._queries = queries if queries is not None else self._settings.github_code_search_queries
        self._max_results = max_results if max_results is not None else self._settings.github_code_max_results

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": ACCEPT_TEXT_MATCH,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _search(self, query: str) -> list[dict[str, Any]]:
        client = await self._get_client()
        resp = await client.get(
            f"{GITHUB_API}/search/code",
            params={"q": query, "per_page": min(self._max_results, 100)},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        items: list[dict[str, Any]] = data.get("items", [])
        return items

    @staticmethod
    def _fragment(item: dict[str, Any]) -> str:
        matches = item.get("text_matches") or []
        return "\n".join(m.get("fragment", "") for m in matches if m.get("fragment"))

    async def poll(self) -> list[RawItem]:
        if not self._token:
            log.info("github_code_skipped_no_token")
            return []
        if not self._queries:
            return []

        items: list[RawItem] = []
        seen: set[str] = set()
        for query in self._queries:
            try:
                results = await self._search(query)
            except httpx.HTTPError as exc:
                log.warning("github_code_search_failed", query=query, error=str(exc))
                continue
            for result in results:
                url = result.get("html_url") or ""
                key = url or f"{result.get('id')}"
                if not key or key in seen:
                    continue
                seen.add(key)
                repo = (result.get("repository") or {}).get("full_name", "")
                path = result.get("path", "")
                fragment = self._fragment(result)
                content = f"# {repo}/{path}\n{fragment}" if fragment else f"# {repo}/{path}"
                external_id = str(result.get("sha") or result.get("id") or key)
                items.append(self.make_raw_item(self.name, external_id, url, content))
                if len(items) >= self._max_results:
                    return items
        return items
