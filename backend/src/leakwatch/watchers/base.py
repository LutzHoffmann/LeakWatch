"""Base watcher abstraction shared by all source pollers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from ..schemas import RawItem


class BaseWatcher(ABC):
    """Abstract base for all leak-source watchers.

    A watcher is responsible for polling exactly one source (e.g. GitHub Gists,
    Pastebin, a Telegram channel) and returning a list of :class:`RawItem`
    instances representing newly discovered content. Downstream stages
    (analyzer, matcher, alerter) operate on these raw items.
    """

    name: str = "base"

    @abstractmethod
    async def poll(self) -> list[RawItem]:
        """Poll the source and return newly discovered raw items.

        Implementations should be idempotent w.r.t. already-seen items: callers
        deduplicate via ``(source, external_id)`` before persisting.
        """
        raise NotImplementedError

    @staticmethod
    def make_raw_item(
        source: str,
        external_id: str,
        url: str,
        content: str,
        fetched_at: datetime | None = None,
    ) -> RawItem:
        return RawItem(
            source=source,
            external_id=external_id,
            url=url,
            content=content,
            fetched_at=fetched_at or datetime.now(UTC).replace(tzinfo=None),
        )
