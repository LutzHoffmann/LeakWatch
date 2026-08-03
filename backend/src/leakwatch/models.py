"""SQLAlchemy ORM models.

The schema models the full core loop:

    RawItem (watcher output) -> Credential (LLM extraction) -> Match (domain match)
    -> Alert (notification sent)

`UserDomain` holds the domains/emails the user wants to monitor. `RawItem` and
`Credential` carry an optional pgvector embedding for future semantic search.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserDomain(Base):
    """A domain (or exact email) the user wants to monitor."""

    __tablename__ = "user_domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_email: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    matches: Mapped[list[Match]] = relationship(back_populates="domain")


class RawItem(Base):
    """Raw text fetched from a source by a watcher."""

    __tablename__ = "raw_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    credentials: Mapped[list[Credential]] = relationship(
        back_populates="raw_item", cascade="all, delete-orphan"
    )


class Credential(Base):
    """A credential extracted from a raw item by the LLM analyzer."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(ForeignKey("raw_items.id", ondelete="CASCADE"), index=True)

    kind: Mapped[str] = mapped_column(String(32), index=True)  # email|password|url|wallet
    value: Mapped[str] = mapped_column(Text, index=True)
    context: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_item: Mapped[RawItem] = relationship(back_populates="credentials")
    matches: Mapped[list[Match]] = relationship(back_populates="credential", cascade="all, delete-orphan")


class Match(Base):
    """A match between a credential and a monitored user domain/email."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id", ondelete="CASCADE"), index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("user_domains.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    credential: Mapped[Credential] = relationship(back_populates="matches")
    domain: Mapped[UserDomain] = relationship(back_populates="matches")
    alerts: Mapped[list[Alert]] = relationship(back_populates="match", cascade="all, delete-orphan")


class Alert(Base):
    """A notification that was sent for a match."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(32))  # email|telegram|webhook
    status: Mapped[str] = mapped_column(String(32), default="sent")  # sent|failed
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match: Mapped[Match] = relationship(back_populates="alerts")
