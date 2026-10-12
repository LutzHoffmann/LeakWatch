"""Matches routes — list credential matches found by the watch pipeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..db import SessionLocal
from ..persistence import load_matches

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.get("")
async def list_matches(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    """Return the most recent matches with their credentials and paired companions."""
    async with SessionLocal() as session:
        matches = await load_matches(session, limit=limit)
    return {"matches": matches}
