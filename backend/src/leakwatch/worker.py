"""ARQ worker — orchestrates the poll -> analyze -> match -> alert core loop.

Run with:

    uv run arq leakwatch.worker.WorkerSettings
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog

from .alerter import Alerter
from .analyzer import LeakAnalyzer
from .config import get_settings
from .llm.openrouter import OpenRouterClient
from .matcher import DomainMatcher, StaticDomainSource
from .schemas import RawItem
from .watchers import BaseWatcher, GitHubGistWatcher, PastebinWatcher

log = structlog.get_logger(__name__)

# A small static list of monitored domains. Phase 2 will replace this with a
# DB-backed DomainSource seeded from the `user_domains` table.
DEFAULT_MONITORED_DOMAINS: tuple[str, ...] = ("example.com",)


def build_watchers() -> list[BaseWatcher]:
    return [GitHubGistWatcher(), PastebinWatcher()]


async def run_watch_cycle(ctx: dict[str, Any]) -> dict[str, int]:
    """Single iteration of the core loop, invoked by the ARQ cron scheduler."""
    settings = get_settings()
    llm = OpenRouterClient()
    analyzer = LeakAnalyzer(llm=llm)
    matcher = DomainMatcher(StaticDomainSource(DEFAULT_MONITORED_DOMAINS))
    alerter = Alerter(settings=settings)

    stats = {"raw_items": 0, "credentials": 0, "matches": 0, "alerts": 0}

    for watcher in build_watchers():
        try:
            items: Sequence[RawItem] = await watcher.poll()
        except Exception as exc:  # noqa: BLE001
            log.warning("watcher_poll_failed", watcher=watcher.name, error=str(exc))
            continue

        stats["raw_items"] += len(items)
        for item in items:
            credentials = await analyzer.extract_credentials(item.content)
            stats["credentials"] += len(credentials)
            if not credentials:
                continue
            matches = await matcher.check(credentials)
            stats["matches"] += len(matches)
            for match in matches:
                alerts = await alerter.send(match)
                stats["alerts"] += len(alerts)

    log.info("watch_cycle_complete", **stats)
    return stats


async def startup(ctx: dict[str, Any]) -> None:
    log.info("leakwatch_worker_starting", model=get_settings().llm_model)


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("leakwatch_worker_stopping")


class WorkerSettings:
    """ARQ worker settings."""

    functions: list[Any] = []
    cron_jobs = [
        {"name": "watch_cycle", "func": run_watch_cycle, "cron": "*/5 * * * *"},
    ]
    on_startup = startup
    on_shutdown = shutdown
