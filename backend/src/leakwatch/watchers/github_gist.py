"""GitHub Gists watcher.

Polls the public GitHub Gists feed (`GET /gists/public`) and returns the raw
content of each newly discovered gist. Authentication is optional but strongly
recommended to raise the rate limit.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import get_settings
from ..schemas import RawItem
from .base import BaseWatcher

GITHUB_API = "https://api.github.com"


class GitHubGistWatcher(BaseWatcher):
    name = "github_gist"

    def __init__(
        self,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
        per_page: int = 50,
    ) -> None:
        self._settings = get_settings()
        self._token = token if token is not None else self._settings.github_token
        self._client = client
        self._per_page = per_page

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _fetch_gists(self) -> list[dict[str, Any]]:
        client = await self._get_client()
        resp = await client.get(
            f"{GITHUB_API}/gists/public",
            params={"per_page": self._per_page},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    async def _fetch_gist_content(self, gist_id: str) -> str:
        client = await self._get_client()
        resp = await client.get(f"{GITHUB_API}/gists/{gist_id}", headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        parts: list[str] = []
        for file_info in data.get("files", {}).values():
            content = file_info.get("content")
            if content:
                parts.append(content)
        return "\n\n".join(parts)

    async def poll(self) -> list[RawItem]:
        gists = await self._fetch_gists()
        items: list[RawItem] = []
        for gist in gists:
            gist_id = gist["id"]
            url = gist.get("html_url", f"https://gist.github.com/{gist_id}")
            try:
                content = await self._fetch_gist_content(gist_id)
            except httpx.HTTPError:
                content = ""
            items.append(self.make_raw_item(self.name, gist_id, url, content))
        return items
