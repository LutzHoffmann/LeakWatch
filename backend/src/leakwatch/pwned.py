"""HaveIBeenPwned Pwned Passwords client — free, no API key required.

Uses the k-anonymity SHA-1 range search: the client hashes the password with
SHA-1, sends only the first 5 hex characters of the hash to the API, and
matches the returned suffix list locally. The full hash (and thus the
password) never leaves the lookup — only a 5-char prefix is disclosed, which
is the privacy property that lets this endpoint stay free and keyless.

Reference: https://haveibeenpwned.com/API/v3#PwnedPasswords
"""

from __future__ import annotations

import hashlib

import httpx
import structlog

from .config import get_settings

log = structlog.get_logger(__name__)


class PwnedPasswordsError(Exception):
    """Raised when the Pwned Passwords API call fails unexpectedly."""


class PwnedPasswordsClient:
    """Async client for the free, keyless Pwned Passwords range API."""

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url if base_url is not None else settings.pwned_base_url).rstrip("/")
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        # HIBP requires a User-Agent on the Pwned Passwords endpoint.
        return {"User-Agent": "LeakWatch"}

    @staticmethod
    def _hash_password(password: str) -> str:
        # SHA-1 is required by the Pwned Passwords API spec; it is not used for
        # any security-sensitive purpose here, only as the lookup key.
        return hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324

    @staticmethod
    def _parse_range(body: str) -> dict[str, int]:
        """Parse the ``SUFFIX:COUNT`` lines returned by the range endpoint."""
        counts: dict[str, int] = {}
        for line in body.splitlines():
            if not line:
                continue
            suffix, _, count = line.partition(":")
            try:
                counts[suffix.strip().upper()] = int(count.strip())
            except ValueError:
                continue
        return counts

    async def check_password(self, password: str) -> int:
        """Return how many times ``password`` has appeared in known breaches (0 if never)."""
        full_hash = self._hash_password(password)
        prefix, suffix = full_hash[:5], full_hash[5:]
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/range/{prefix}", headers=self._headers())
        if resp.status_code != 200:
            raise PwnedPasswordsError(f"Pwned Passwords request failed: {resp.status_code}")
        counts = self._parse_range(resp.text)
        return counts.get(suffix, 0)
