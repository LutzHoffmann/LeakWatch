"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from leakwatch.llm.openrouter import OpenRouterClient
from leakwatch.schemas import Credential, CredentialKind, RawItem


class MockLLM(OpenRouterClient):
    """LLM stub returning a canned JSON response."""

    def __init__(self, response: dict[str, Any] | str) -> None:
        self._response = response
        # bypass parent __init__ so no real http client / settings are needed
        self._client = None  # type: ignore[assignment]

    async def chat_json(self, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]:  # type: ignore[override]
        if isinstance(self._response, str):
            raise type("LLMError", (RuntimeError,), {})("forced failure")
        return self._response


@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM(
        {
            "emails": ["alice@example.com", "bob@leak.test"],
            "passwords": ["hunter2"],
            "urls": ["https://dump.example/x"],
            "wallets": ["0xabc123"],
        }
    )


@pytest.fixture
def sample_raw_item() -> RawItem:
    return RawItem(
        source="github_gist",
        external_id="abc123",
        url="https://gist.github.com/abc123",
        content="email: alice@example.com pass: hunter2",
    )


@pytest.fixture
def email_credential() -> Credential:
    return Credential(kind=CredentialKind.EMAIL, value="alice@example.com")


@pytest.fixture
def mock_httpx_client() -> httpx.AsyncClient:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    return httpx.AsyncClient(transport=transport)


@pytest.fixture
async def async_noop() -> AsyncIterator[None]:
    yield None
