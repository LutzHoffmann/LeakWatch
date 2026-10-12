"""OpenRouter chat client used to drive GLM-5.2 (and other models).

The client is a thin async wrapper around the OpenRouter `/chat/completions`
endpoint. It supports:

* a JSON-mode system+user prompt helper (:meth:`chat_json`),
* retries with exponential backoff via :mod:`tenacity`,
* configurable model / timeout through :class:`Settings`.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings

log = structlog.get_logger(__name__)


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns non-JSON content."""


class OpenRouterClient:
    """Async client for the OpenRouter chat completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._base_url = (base_url or settings.llm_base_url).rstrip("/")
        self._model = model or settings.llm_model
        self._timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise LLMError("LLM_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data
        raise LLMError("unreachable")  # pragma: no cover

    async def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
    ) -> str:
        """Run a chat completion and return the assistant message text."""
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = await self._post(payload)
        try:
            content: str = data["choices"][0]["message"]["content"]
            return content
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected LLM response shape: {data!r}") from exc

    async def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Run a chat completion and parse the response as JSON.

        The prompt is augmented with an instruction to return *only* valid JSON.
        Fenced ```json blocks are tolerated.
        """
        system = f"{system}\n\nRespond with ONLY valid JSON, no prose, no code fences."
        raw = await self.chat(system, user, temperature=temperature)
        return parse_json(raw)


def parse_json(raw: str) -> dict[str, Any]:
    """Parse an LLM response that should contain JSON, tolerating code fences."""
    text = raw.strip()
    if text.startswith("```"):
        # strip leading ```json or ``` and trailing ```
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM did not return valid JSON: {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise LLMError(f"LLM JSON is not an object: {parsed!r}")
    return parsed
