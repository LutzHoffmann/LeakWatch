"""Domain matcher — checks extracted credentials against monitored domains/emails."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

import structlog

from .schemas import Credential, CredentialKind, Match

log = structlog.get_logger(__name__)


class DomainSource(Protocol):
    """Anything that can provide the set of monitored user domains/emails."""

    async def get_user_domains(self) -> Sequence[str]: ...


class StaticDomainSource:
    """In-memory domain source, handy for tests and CLI one-offs."""

    def __init__(self, domains: Iterable[str]) -> None:
        self._domains = list(domains)

    async def get_user_domains(self) -> Sequence[str]:
        return list(self._domains)


class DomainMatcher:
    """Match extracted credentials against monitored domains/emails.

    A credential matches a monitored value when:
    * the credential is an email and its domain part equals a monitored domain,
      or the full email equals a monitored email, or
    * the monitored value (domain/email) appears as a substring in the
      credential value or its context.
    """

    def __init__(self, source: DomainSource) -> None:
        self._source = source

    @staticmethod
    def _email_domain(email: str) -> str | None:
        if "@" not in email:
            return None
        return email.rsplit("@", 1)[1].lower()

    async def check(self, credentials: Sequence[Credential]) -> list[Match]:
        domains = await self._source.get_user_domains()
        if not domains or not credentials:
            return []
        monitored = [d.lower() for d in domains]
        matches: list[Match] = []

        for cred in credentials:
            for value in monitored:
                reason = self._match_reason(cred, value)
                if reason:
                    matches.append(Match(credential=cred, domain_value=value, reason=reason))
        return matches

    @staticmethod
    def _match_reason(cred: Credential, monitored: str) -> str:
        target = cred.value.lower()
        context = (cred.context or "").lower()
        if cred.kind == CredentialKind.EMAIL:
            domain = DomainMatcher._email_domain(cred.value)
            if domain and (domain == monitored or domain.endswith(f".{monitored}")):
                return f"email domain matches {monitored}"
            if target == monitored:
                return f"email equals {monitored}"
        if monitored in target:
            return f"monitored value '{monitored}' found in credential"
        if context and monitored in context:
            return f"monitored value '{monitored}' found in context"
        return ""
