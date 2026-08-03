"""Leak analyzer — extracts structured credentials from raw text via GLM-5.2."""

from __future__ import annotations

import structlog

from .llm.openrouter import LLMError, OpenRouterClient
from .schemas import Credential, CredentialKind, LLMExtractionResult

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """\
You are a security analyst. Extract credentials from the given text.

Return JSON with these keys (omit a key if nothing is found):
- "emails": list of email addresses (with domain)
- "passwords": list of passwords, only if clearly recognizable as such
- "urls": list of URLs pointing to leak dumps or relevant resources
- "wallets": list of cryptocurrency wallet addresses

Rules:
- Output ONLY the JSON object, no explanation.
- Deduplicate entries.
- Do not invent data that is not present in the text.
"""


class LeakAnalyzer:
    """Turn raw leak text into structured :class:`Credential` objects via an LLM."""

    def __init__(self, llm: OpenRouterClient | None = None) -> None:
        self._llm = llm or OpenRouterClient()

    async def extract_credentials(self, text: str) -> list[Credential]:
        if not text or not text.strip():
            return []

        try:
            data = await self._llm.chat_json(SYSTEM_PROMPT, text[:8000])
        except LLMError as exc:
            log.warning("llm_extraction_failed", error=str(exc))
            return []

        try:
            result = LLMExtractionResult.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError plus others
            log.warning("llm_extraction_parse_failed", error=str(exc), raw=data)
            return []

        credentials: list[Credential] = []
        for email in result.emails:
            credentials.append(Credential(kind=CredentialKind.EMAIL, value=email))
        for pw in result.passwords:
            credentials.append(Credential(kind=CredentialKind.PASSWORD, value=pw))
        for url in result.urls:
            credentials.append(Credential(kind=CredentialKind.URL, value=url))
        for wallet in result.wallets:
            credentials.append(Credential(kind=CredentialKind.WALLET, value=wallet))
        return credentials
