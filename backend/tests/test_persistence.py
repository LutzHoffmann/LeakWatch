"""Tests for the persistence layer (against in-memory SQLite)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from leakwatch import models, persistence
from leakwatch.persistence import (
    DbDomainSource,
    alert_status_from_message,
    get_or_create_raw_item,
    get_or_create_user_domain,
    load_matches,
    load_user_domains,
    map_credentials_to_models,
    persist_alert,
    persist_credentials,
    persist_match,
    seed_default_domains,
)
from leakwatch.schemas import Credential, CredentialKind, RawItem


@pytest.mark.asyncio
async def test_get_or_create_user_domain_is_idempotent(sqlite_session: Any) -> None:
    d1 = await get_or_create_user_domain(sqlite_session, "example.com")
    d2 = await get_or_create_user_domain(sqlite_session, "example.com")
    assert d1.id == d2.id
    await sqlite_session.commit()
    rows = await load_user_domains(sqlite_session)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_seed_default_domains_creates_defaults(sqlite_session: Any) -> None:
    await seed_default_domains(sqlite_session)
    await sqlite_session.commit()
    values = [d.value for d in await load_user_domains(sqlite_session)]
    assert "example.com" in values


@pytest.mark.asyncio
async def test_get_or_create_raw_item_dedups(sqlite_session: Any) -> None:
    item = RawItem(source="pastebin", external_id="abc12345", url="u", content="c")
    first = await get_or_create_raw_item(sqlite_session, item)
    second = await get_or_create_raw_item(sqlite_session, item)
    assert first is not None
    assert second is None
    await sqlite_session.commit()
    rows = (await sqlite_session.execute(select(models.RawItem))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_persist_credentials_creates_rows_linked_to_raw_item(sqlite_session: Any) -> None:
    raw = await get_or_create_raw_item(
        sqlite_session,
        RawItem(source="s", external_id="1", url="u", content="c"),
    )
    creds = [
        Credential(kind=CredentialKind.EMAIL, value="a@example.com"),
        Credential(kind=CredentialKind.PASSWORD, value="hunter2"),
    ]
    rows = await persist_credentials(sqlite_session, raw.id, creds)
    assert len(rows) == 2
    assert {r.kind for r in rows} == {"email", "password"}
    assert all(r.raw_item_id == raw.id for r in rows)
    await sqlite_session.commit()


@pytest.mark.asyncio
async def test_persist_match_and_alert_chain(sqlite_session: Any) -> None:
    domain = await get_or_create_user_domain(sqlite_session, "example.com")
    raw = await get_or_create_raw_item(
        sqlite_session,
        RawItem(source="s", external_id="1", url="u", content="c"),
    )
    cred_rows = await persist_credentials(
        sqlite_session,
        raw.id,
        [Credential(kind=CredentialKind.EMAIL, value="a@example.com")],
    )
    match = await persist_match(sqlite_session, cred_rows[0].id, domain.id, "email domain matches")
    await persist_alert(sqlite_session, match.id, "telegram", "sent", "hello")
    await sqlite_session.commit()

    match_rows = (await sqlite_session.execute(select(models.Match))).scalars().all()
    alert_rows = (await sqlite_session.execute(select(models.Alert))).scalars().all()
    assert len(match_rows) == 1
    assert match_rows[0].credential_id == cred_rows[0].id
    assert match_rows[0].domain_id == domain.id
    assert len(alert_rows) == 1
    assert alert_rows[0].match_id == match.id
    assert alert_rows[0].channel == "telegram"


@pytest.mark.asyncio
async def test_persist_credentials_stores_pair_id(sqlite_session: Any) -> None:
    raw = await get_or_create_raw_item(
        sqlite_session,
        RawItem(source="s", external_id="1", url="u", content="c"),
    )
    creds = [
        Credential(kind=CredentialKind.EMAIL, value="a@example.com", pair_id="pair-1"),
        Credential(kind=CredentialKind.PASSWORD, value="hunter2", pair_id="pair-1"),
        Credential(kind=CredentialKind.EMAIL, value="b@example.com"),
    ]
    rows = await persist_credentials(sqlite_session, raw.id, creds)
    await sqlite_session.commit()
    pair_rows = [r for r in rows if r.pair_id == "pair-1"]
    standalone = [r for r in rows if r.pair_id is None]
    assert len(pair_rows) == 2
    assert len(standalone) == 1
    assert {r.kind for r in pair_rows} == {"email", "password"}


@pytest.mark.asyncio
async def test_load_matches_returns_pairs_and_source(sqlite_session: Any) -> None:
    domain = await get_or_create_user_domain(sqlite_session, "example.com")
    raw = await get_or_create_raw_item(
        sqlite_session,
        RawItem(source="pastebin", external_id="abc12345", url="https://pastebin.com/abc12345", content="c"),
    )
    cred_rows = await persist_credentials(
        sqlite_session,
        raw.id,
        [
            Credential(kind=CredentialKind.EMAIL, value="alice@example.com", pair_id="pair-1"),
            Credential(kind=CredentialKind.PASSWORD, value="hunter2", pair_id="pair-1"),
        ],
    )
    email_row = next(r for r in cred_rows if r.kind == "email")
    await persist_match(sqlite_session, email_row.id, domain.id, "domain match")
    await sqlite_session.commit()

    matches = await load_matches(sqlite_session)
    assert len(matches) == 1
    m = matches[0]
    assert m["domain"] == "example.com"
    assert m["credential"]["value"] == "alice@example.com"
    assert m["paired_credential"]["kind"] == "password"
    assert m["paired_credential"]["value"] == "hunter2"
    assert m["source"] == "pastebin"
    assert m["url"] == "https://pastebin.com/abc12345"


@pytest.mark.asyncio
async def test_db_domain_source_returns_values(sqlite_session: Any) -> None:
    await get_or_create_user_domain(sqlite_session, "example.com")
    await get_or_create_user_domain(sqlite_session, "other.test", is_email=False)
    await sqlite_session.commit()
    source = DbDomainSource(sqlite_session)
    values = list(await source.get_user_domains())
    assert set(values) == {"example.com", "other.test"}


def test_alert_status_from_message() -> None:
    assert alert_status_from_message("sent ok") == "sent"
    assert alert_status_from_message("failed: boom") == "failed"


def test_map_credentials_to_models_aligns_by_identity() -> None:
    creds = [
        Credential(kind=CredentialKind.EMAIL, value="a@example.com"),
        Credential(kind=CredentialKind.PASSWORD, value="x"),
    ]

    class FakeModel:
        def __init__(self, i: int) -> None:
            self.id = i

    models_ = [FakeModel(1), FakeModel(2)]
    mapping = map_credentials_to_models(creds, models_)
    assert mapping[id(creds[0])].id == 1
    assert mapping[id(creds[1])].id == 2


def test_default_monitored_domains_constant() -> None:
    assert "example.com" in persistence.DEFAULT_MONITORED_DOMAINS
