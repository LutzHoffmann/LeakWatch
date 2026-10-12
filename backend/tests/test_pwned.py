"""Tests for the Pwned Passwords client."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from leakwatch.pwned import PwnedPasswordsClient, PwnedPasswordsError


def _sha1(password: str) -> str:
    return hashlib.sha1(password.encode("utf-8")).hexdigest().upper()


def test_parse_range_handles_suffix_counts() -> None:
    body = "ABCD1:3\nABCDE:10\n\nGARBAGE:nope\n"
    counts = PwnedPasswordsClient._parse_range(body)
    assert counts == {"ABCD1": 3, "ABCDE": 10}


@pytest.mark.asyncio
async def test_check_password_breached_returns_count() -> None:
    password = "password"
    full = _sha1(password)
    prefix, suffix = full[:5], full[5:]
    body = f"00001:1\n{suffix}:42\nFFFFF:9\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/range/{prefix}"
        assert request.headers["User-Agent"] == "LeakWatch"
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    pwned = PwnedPasswordsClient(client=client)

    count = await pwned.check_password(password)

    assert count == 42
    await client.aclose()


@pytest.mark.asyncio
async def test_check_password_not_breached_returns_zero() -> None:
    password = "password"
    full = _sha1(password)
    prefix = full[:5]
    # Return entries but NOT the matching suffix.
    body = "00001:1\nFFFFF:9\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/range/{prefix}"
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    pwned = PwnedPasswordsClient(client=client)

    count = await pwned.check_password(password)

    assert count == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_check_password_api_error_raises() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500, text="boom"))
    client = httpx.AsyncClient(transport=transport)
    pwned = PwnedPasswordsClient(client=client)

    with pytest.raises(PwnedPasswordsError):
        await pwned.check_password("whatever")
    await client.aclose()


def test_hash_password_is_uppercase_sha1() -> None:
    assert PwnedPasswordsClient._hash_password("password") == _sha1("password")
    assert PwnedPasswordsClient._hash_password("password") == _sha1("password").upper()
