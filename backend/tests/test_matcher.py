"""Tests for the domain matcher."""

from __future__ import annotations

import pytest

from leakwatch.matcher import DomainMatcher, StaticDomainSource
from leakwatch.schemas import Credential, CredentialKind


@pytest.mark.asyncio
async def test_matcher_no_credentials_returns_empty() -> None:
    matcher = DomainMatcher(StaticDomainSource(["example.com"]))
    assert await matcher.check([]) == []


@pytest.mark.asyncio
async def test_matcher_no_domains_returns_empty() -> None:
    matcher = DomainMatcher(StaticDomainSource([]))
    creds = [Credential(kind=CredentialKind.EMAIL, value="a@example.com")]
    assert await matcher.check(creds) == []


@pytest.mark.asyncio
async def test_matcher_matches_email_domain() -> None:
    matcher = DomainMatcher(StaticDomainSource(["example.com"]))
    creds = [Credential(kind=CredentialKind.EMAIL, value="alice@example.com")]
    matches = await matcher.check(creds)
    assert len(matches) == 1
    assert matches[0].domain_value == "example.com"
    assert "email domain matches" in matches[0].reason


@pytest.mark.asyncio
async def test_matcher_matches_subdomain() -> None:
    matcher = DomainMatcher(StaticDomainSource(["example.com"]))
    creds = [Credential(kind=CredentialKind.EMAIL, value="alice@sub.example.com")]
    matches = await matcher.check(creds)
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_matcher_matches_exact_email() -> None:
    matcher = DomainMatcher(StaticDomainSource(["alice@example.com"]))
    creds = [Credential(kind=CredentialKind.EMAIL, value="alice@example.com")]
    matches = await matcher.check(creds)
    assert len(matches) == 1
    assert "email equals" in matches[0].reason


@pytest.mark.asyncio
async def test_matcher_matches_substring_in_value() -> None:
    matcher = DomainMatcher(StaticDomainSource(["example.com"]))
    creds = [Credential(kind=CredentialKind.URL, value="https://dump.example.com/x")]
    matches = await matcher.check(creds)
    assert len(matches) == 1
    assert "found in credential" in matches[0].reason


@pytest.mark.asyncio
async def test_matcher_matches_substring_in_context() -> None:
    matcher = DomainMatcher(StaticDomainSource(["example.com"]))
    creds = [Credential(kind=CredentialKind.PASSWORD, value="hunter2", context="from example.com leak")]
    matches = await matcher.check(creds)
    assert len(matches) == 1
    assert "found in context" in matches[0].reason


@pytest.mark.asyncio
async def test_matcher_no_match_when_unrelated() -> None:
    matcher = DomainMatcher(StaticDomainSource(["example.com"]))
    creds = [Credential(kind=CredentialKind.EMAIL, value="alice@other.test")]
    assert await matcher.check(creds) == []


@pytest.mark.asyncio
async def test_matcher_is_case_insensitive() -> None:
    matcher = DomainMatcher(StaticDomainSource(["Example.COM"]))
    creds = [Credential(kind=CredentialKind.EMAIL, value="alice@example.com")]
    matches = await matcher.check(creds)
    assert len(matches) == 1
