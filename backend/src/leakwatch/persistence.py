"""Database persistence layer.

Repository-style async functions that turn the in-memory DTOs produced by the
core loop (:class:`leakwatch.schemas.RawItem`, :class:`Credential`, :class:`Match`)
into ORM rows, plus a DB-backed :class:`DomainSource`.

All functions take an :class:`AsyncSession` so they can be unit-tested against
an in-memory SQLite engine without touching Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from . import models
from .schemas import Credential as CredentialDTO
from .schemas import RawItem

DEFAULT_MONITORED_DOMAINS: tuple[str, ...] = ("example.com",)


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables if they do not exist yet."""
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


async def seed_default_domains(session: AsyncSession) -> None:
    """Ensure the default monitored domains exist as ``UserDomain`` rows."""
    for value in DEFAULT_MONITORED_DOMAINS:
        await get_or_create_user_domain(session, value, is_email=False)


async def get_or_create_user_domain(
    session: AsyncSession, value: str, is_email: bool = False
) -> models.UserDomain:
    """Return the ``UserDomain`` for ``value``, creating it if necessary."""
    stmt = select(models.UserDomain).where(models.UserDomain.value == value)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    domain = models.UserDomain(value=value, is_email=is_email)
    session.add(domain)
    await session.flush()
    return domain


async def load_user_domains(session: AsyncSession) -> list[models.UserDomain]:
    """Return all monitored user domains/emails."""
    stmt = select(models.UserDomain)
    return list((await session.execute(stmt)).scalars().all())


async def get_or_create_raw_item(
    session: AsyncSession, item: RawItem
) -> models.RawItem | None:
    """Insert a raw item if (source, external_id) is new; return None if it already exists.

    Dedup is keyed on ``(source, external_id)`` so re-polling a source does not
    create duplicate rows.
    """
    stmt = select(models.RawItem).where(
        models.RawItem.source == item.source,
        models.RawItem.external_id == item.external_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return None
    raw = models.RawItem(
        source=item.source,
        external_id=item.external_id,
        url=item.url,
        content=item.content,
        fetched_at=item.fetched_at,
    )
    session.add(raw)
    await session.flush()
    return raw


async def persist_credentials(
    session: AsyncSession, raw_item_id: int, credentials: Sequence[CredentialDTO]
) -> list[models.Credential]:
    """Persist extracted credentials for a raw item, in order."""
    rows: list[models.Credential] = []
    for cred in credentials:
        row = models.Credential(
            raw_item_id=raw_item_id,
            kind=cred.kind.value,
            value=cred.value,
            context=cred.context,
            pair_id=cred.pair_id,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def persist_match(
    session: AsyncSession, credential_id: int, domain_id: int, reason: str
) -> models.Match:
    match = models.Match(credential_id=credential_id, domain_id=domain_id, reason=reason)
    session.add(match)
    await session.flush()
    return match


async def persist_alert(
    session: AsyncSession,
    match_id: int,
    channel: str,
    status: str,
    message: str,
) -> models.Alert:
    alert = models.Alert(
        match_id=match_id, channel=channel, status=status, message=message
    )
    session.add(alert)
    await session.flush()
    return alert


class DbDomainSource:
    """DomainSource backed by the ``user_domains`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_domains(self) -> Sequence[str]:
        domains = await load_user_domains(self._session)
        return [d.value for d in domains]


def alert_status_from_message(message: str) -> str:
    """Derive an alert status from the payload message produced by the Alerter."""
    return "failed" if message.startswith("failed") else "sent"


def map_credentials_to_models(
    credentials: Sequence[CredentialDTO], models_: Sequence[models.Credential]
) -> dict[int, models.Credential]:
    """Map ``id(schema_credential) -> ORM model`` for later match persistence."""
    return {id(cred): model for cred, model in zip(credentials, models_, strict=False)}


async def load_matches(session: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
    """Return recent matches with their credentials, paired credentials and source.

    Each entry is a plain dict ready for JSON serialisation:

    * ``id``, ``created_at`` — match row
    * ``domain`` — monitored domain/email that matched
    * ``reason`` — match reason
    * ``credential`` — the matched credential (kind, value, pair_id)
    * ``paired_credential`` — the companion credential sharing ``pair_id``
      (e.g. the password paired with the matched email), or ``None``
    * ``source``, ``url``, ``fetched_at`` — the raw item the credential came from
    """
    stmt = (
        select(
            models.Match,
            models.Credential,
            models.UserDomain,
            models.RawItem,
        )
        .join(models.Credential, models.Match.credential_id == models.Credential.id)
        .join(models.UserDomain, models.Match.domain_id == models.UserDomain.id)
        .join(models.RawItem, models.Credential.raw_item_id == models.RawItem.id)
        .order_by(models.Match.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    # Collect pair_ids of matched credentials so we can fetch their companions
    # (e.g. the password paired with a matched email) in a single query.
    pair_keys: set[tuple[int, str]] = {
        (raw.id, cred.pair_id)
        for _match, cred, _domain, raw in rows
        if cred.pair_id is not None
    }
    companions: dict[tuple[int, str], list[models.Credential]] = {}
    if pair_keys:
        pair_stmt = select(models.Credential).where(models.Credential.pair_id.isnot(None))
        for cred in (await session.execute(pair_stmt)).scalars().all():
            key = (cred.raw_item_id, cred.pair_id)
            if key in pair_keys:
                companions.setdefault(key, []).append(cred)

    matches: list[dict[str, Any]] = []
    for match, cred, domain, raw in rows:
        companion = None
        if cred.pair_id is not None:
            for cand in companions.get((raw.id, cred.pair_id), []):
                if cand.kind != cred.kind:
                    companion = {
                        "kind": cand.kind,
                        "value": cand.value,
                        "pair_id": cand.pair_id,
                    }
                    break
        matches.append(
            {
                "id": match.id,
                "created_at": match.created_at.isoformat() if match.created_at else None,
                "domain": domain.value,
                "reason": match.reason,
                "credential": {
                    "kind": cred.kind,
                    "value": cred.value,
                    "pair_id": cred.pair_id,
                },
                "paired_credential": companion,
                "source": raw.source,
                "url": raw.url,
                "fetched_at": raw.fetched_at.isoformat() if raw.fetched_at else None,
            }
        )
    return matches


__all__: list[Any] = [
    "DEFAULT_MONITORED_DOMAINS",
    "DbDomainSource",
    "alert_status_from_message",
    "get_or_create_raw_item",
    "get_or_create_user_domain",
    "init_db",
    "load_matches",
    "load_user_domains",
    "map_credentials_to_models",
    "persist_alert",
    "persist_credentials",
    "persist_match",
    "seed_default_domains",
]
