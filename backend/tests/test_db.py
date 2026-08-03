"""Tests for the DB session helpers."""

from __future__ import annotations

import pytest

from leakwatch import db


@pytest.mark.asyncio
async def test_get_session_yields_session(monkeypatch: pytest.MonkeyPatch) -> None:
    yielded: list = []

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(db, "SessionLocal", FakeSession)

    async for session in db.get_session():
        yielded.append(session)

    assert len(yielded) == 1
    assert isinstance(yielded[0], FakeSession)
