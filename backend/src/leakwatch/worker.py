"""ARQ worker — orchestrates the poll -> analyze -> match -> alert core loop.

Each cycle:
  1. watchers poll sources -> RawItems
  2. dedup + persist RawItems
  3. analyzer extracts Credentials (GLM-5.2) -> persist
  4. matcher checks against user_domains from DB -> persist Matches
  5. alerter sends notifications -> persist Alerts

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
from .db import SessionLocal
from .llm.openrouter import OpenRouterClient
from .matcher import DomainMatcher, StaticDomainSource
from .persistence import (
    alert_status_from_message,
    get_or_create_raw_item,
    load_user_domains,
    map_credentials_to_models,
    persist_alert,
    persist_credentials,
    persist_match,
    seed_default_domains,
)
from .schemas import RawItem
from .watchers import (
    BaseWatcher,
    GitHubCodeSearchWatcher,
    GitHubGistWatcher,
    PastebinWatcher,
)

log = structlog.get_logger(__name__)


def build_watchers() -> list[BaseWatcher]:
    return [GitHubGistWatcher(), GitHubCodeSearchWatcher(), PastebinWatcher()]


async def run_watch_cycle(ctx: dict[str, Any]) -> dict[str, int]:
    """Single iteration of the core loop, invoked by the ARQ cron scheduler."""
    settings = get_settings()
    llm = OpenRouterClient()
    analyzer = LeakAnalyzer(llm=llm)
    alerter = Alerter(settings=settings)

    stats = {"raw_items": 0, "credentials": 0, "matches": 0, "alerts": 0}

    async with SessionLocal() as session:
        domains = await load_user_domains(session)
        if not domains:
            await seed_default_domains(session)
            domains = await load_user_domains(session)
        domain_map = {d.value.lower(): d.id for d in domains}
        matcher = DomainMatcher(StaticDomainSource([d.value for d in domains]))

        for watcher in build_watchers():
            try:
                items: Sequence[RawItem] = await watcher.poll()
            except Exception as exc:  # noqa: BLE001
                log.warning("watcher_poll_failed", watcher=watcher.name, error=str(exc))
                continue

            for item in items:
                raw = await get_or_create_raw_item(session, item)
                if raw is None:
                    continue
                stats["raw_items"] += 1

                credentials = await analyzer.extract_credentials(item.content)
                if not credentials:
                    continue
                cred_models = await persist_credentials(session, raw.id, credentials)
                stats["credentials"] += len(credentials)
                cred_to_model = map_credentials_to_models(credentials, cred_models)

                matches = await matcher.check(credentials)
                for match in matches:
                    cred_model = cred_to_model.get(id(match.credential))
                    if cred_model is None:
                        continue
                    domain_id = domain_map.get(match.domain_value)
                    if domain_id is None:
                        continue
                    match_row = await persist_match(
                        session, cred_model.id, domain_id, match.reason
                    )
                    stats["matches"] += 1

                    payloads = await alerter.send(match)
                    for payload in payloads:
                        await persist_alert(
                            session,
                            match_row.id,
                            payload.channel,
                            alert_status_from_message(payload.message),
                            payload.message,
                        )
                        stats["alerts"] += 1

        await session.commit()

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
