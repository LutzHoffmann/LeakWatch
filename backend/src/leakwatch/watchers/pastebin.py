"""Pastebin watcher — Phase 1 stub.

Pastebin's public archive (`/archive`) is heavily rate-limited and requires
scraping. This stub returns an empty list and is meant to be filled in with a
real implementation (e.g. via the scraping API or a third-party mirror) during
Phase 1.
"""

from __future__ import annotations

from .base import BaseWatcher


class PastebinWatcher(BaseWatcher):
    name = "pastebin"

    async def poll(self) -> list:  # type: ignore[type-arg]
        # TODO(Phase 1): scrape https://pastebin.com/archive, fetch each paste's raw
        # body via https://pastebin.com/raw/<id> and emit RawItems.
        return []
