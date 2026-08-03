"""Tests for the LLM OpenRouter client."""

from __future__ import annotations

import httpx
import pytest

from leakwatch.llm.openrouter import LLMError, OpenRouterClient


def _chat_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def test_openrouter_requires_api_key() -> None:
    client = OpenRouterClient(api_key="")
    with pytest.raises(LLMError):
        client._headers()


@pytest.mark.asyncio
async def test_openrouter_chat_returns_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer k"
        body = httpx.Response(200, json=_chat_response("hello"))
        return body

    transport = httpx.MockTransport(handler)
    client = OpenRouterClient(api_key="k", client=httpx.AsyncClient(transport=transport))
    out = await client.chat("sys", "usr")
    assert out == "hello"


@pytest.mark.asyncio
async def test_openrouter_chat_json_parses() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=_chat_response('{"emails": ["a@b.com"]}'))
    )
    client = OpenRouterClient(api_key="k", client=httpx.AsyncClient(transport=transport))
    data = await client.chat_json("sys", "usr")
    assert data == {"emails": ["a@b.com"]}


@pytest.mark.asyncio
async def test_openrouter_chat_bad_shape_raises() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"nope": 1}))
    client = OpenRouterClient(api_key="k", client=httpx.AsyncClient(transport=transport))
    with pytest.raises(LLMError):
        await client.chat("sys", "usr")


@pytest.mark.asyncio
async def test_openrouter_retries_on_http_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, json=_chat_response("ok"))

    transport = httpx.MockTransport(handler)
    client = OpenRouterClient(api_key="k", client=httpx.AsyncClient(transport=transport))
    out = await client.chat("sys", "usr")
    assert out == "ok"
    assert calls["n"] == 3
