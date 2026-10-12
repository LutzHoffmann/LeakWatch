"""Live LLM smoke test against the configured provider (OpenRouter or ZAI/Zhipu).

These tests are skipped by default. They run only when a real API key is
provided via the environment, so they never break CI and never cost credits
on a fresh checkout.

Set to enable:

    LLM_API_KEY=<key> LLM_BASE_URL=https://api.z.ai/api/paas/v4 LLM_MODEL=glm-5.2 \
        uv run pytest tests/test_llm_live.py -m live

or against OpenRouter:

    LLM_API_KEY=<sk-or-...> uv run pytest tests/test_llm_live.py -m live
"""

from __future__ import annotations

import os

import pytest

from leakwatch.analyzer import LeakAnalyzer
from leakwatch.config import get_settings
from leakwatch.llm.openrouter import OpenRouterClient
from leakwatch.schemas import CredentialKind


def _live_enabled() -> bool:
    # Live tests only run when BOTH a key is configured AND the user explicitly
    # opts in via LEAKWATCH_LIVE=1, so a normal `uv run pytest` never burns
    # provider quota.
    return bool(get_settings().llm_api_key) and os.getenv("LEAKWATCH_LIVE") == "1"


pytestmark = pytest.mark.skipif(
    not _live_enabled(),
    reason="live tests require LLM_API_KEY and LEAKWATCH_LIVE=1 (opt-in to avoid burning quota)",
)

_LIVE = pytest.mark.live


@_LIVE
@pytest.mark.asyncio
async def test_live_chat_returns_text() -> None:
    client = OpenRouterClient()
    text = await client.chat("You are a helpful assistant.", "Say 'pong' and nothing else.")
    assert isinstance(text, str)
    assert text.strip()


@_LIVE
@pytest.mark.asyncio
async def test_live_chat_json_returns_object() -> None:
    client = OpenRouterClient()
    data = await client.chat_json(
        "Return a JSON object with a single key 'ok' set to true.",
        "Go.",
    )
    assert isinstance(data, dict)
    assert data.get("ok") is True


@_LIVE
@pytest.mark.asyncio
async def test_live_analyzer_extracts_email() -> None:
    """End-to-end: the real LLM extracts an email from a sample leak snippet."""
    analyzer = LeakAnalyzer()
    sample = (
        "db dump leaked today:\n"
        "user: alice@example.com : hunter2\n"
        "user: bob@leak.test : correcthorse\n"
    )
    credentials = await analyzer.extract_credentials(sample)
    emails = [c.value for c in credentials if c.kind == CredentialKind.EMAIL]
    assert "alice@example.com" in emails
    assert "bob@leak.test" in emails
