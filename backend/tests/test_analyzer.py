"""Tests for the LLM analyzer."""

from __future__ import annotations

from typing import Any

import pytest

from leakwatch.analyzer import LeakAnalyzer
from leakwatch.llm.openrouter import LLMError, parse_json
from leakwatch.schemas import CredentialKind


@pytest.mark.asyncio
async def test_extract_credentials_returns_structured_list(mock_llm: Any) -> None:
    analyzer = LeakAnalyzer(llm=mock_llm)
    creds = await analyzer.extract_credentials("some raw text")

    kinds = {c.kind for c in creds}
    assert kinds == {CredentialKind.EMAIL, CredentialKind.PASSWORD, CredentialKind.URL, CredentialKind.WALLET}
    emails = [c.value for c in creds if c.kind == CredentialKind.EMAIL]
    assert emails == ["alice@example.com", "bob@leak.test"]
    # No pairs in the canned response -> all credentials are standalone.
    assert all(c.pair_id is None for c in creds)


@pytest.mark.asyncio
async def test_extract_credentials_pairs_email_and_password() -> None:
    class PairLLM:
        async def chat_json(self, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]:
            return {
                "pairs": [
                    {"email": "alice@example.com", "password": "hunter2"},
                    {"email": "bob@leak.test", "password": "correcthorse"},
                ],
                "emails": ["carol@example.com"],
                "passwords": [],
                "urls": [],
                "wallets": [],
            }

    analyzer = LeakAnalyzer(llm=PairLLM())  # type: ignore[arg-type]
    creds = await analyzer.extract_credentials("dump text")

    emails = [c for c in creds if c.kind == CredentialKind.EMAIL]
    passwords = [c for c in creds if c.kind == CredentialKind.PASSWORD]
    # 2 paired emails + 1 standalone email
    assert len(emails) == 3
    assert len(passwords) == 2
    # Paired email+password share a pair_id; standalone email has none.
    paired_emails = [c for c in emails if c.pair_id is not None]
    assert len(paired_emails) == 2
    for pw in passwords:
        assert pw.pair_id is not None
        matching = [e for e in paired_emails if e.pair_id == pw.pair_id]
        assert len(matching) == 1
    standalone = [c for c in emails if c.pair_id is None]
    assert [c.value for c in standalone] == ["carol@example.com"]


@pytest.mark.asyncio
async def test_extract_credentials_empty_text_returns_empty() -> None:
    analyzer = LeakAnalyzer(llm=None)
    assert await analyzer.extract_credentials("") == []
    assert await analyzer.extract_credentials("   \n  ") == []


@pytest.mark.asyncio
async def test_extract_credentials_handles_llm_failure() -> None:
    class FailingLLM:
        async def chat_json(self, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]:
            raise LLMError("boom")

    analyzer = LeakAnalyzer(llm=FailingLLM())  # type: ignore[arg-type]
    assert await analyzer.extract_credentials("text") == []


@pytest.mark.asyncio
async def test_extract_credentials_handles_invalid_shape() -> None:
    class BadShapeLLM:
        async def chat_json(self, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]:
            return {"not": "a valid shape"}  # missing keys -> all defaults

    analyzer = LeakAnalyzer(llm=BadShapeLLM())  # type: ignore[arg-type]
    creds = await analyzer.extract_credentials("text")
    assert creds == []


def test_parse_json_plain() -> None:
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced_block() -> None:
    raw = "```json\n{\"a\": 2}\n```"
    assert parse_json(raw) == {"a": 2}


def test_parse_json_invalid_raises() -> None:
    with pytest.raises(LLMError):
        parse_json("not json at all")


def test_parse_json_non_object_raises() -> None:
    with pytest.raises(LLMError):
        parse_json("[1, 2, 3]")
