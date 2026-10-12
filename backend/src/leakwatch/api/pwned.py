"""Pwned Passwords routes — free, keyless password breach check for the frontend."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..pwned import PwnedPasswordsClient, PwnedPasswordsError

router = APIRouter(prefix="/api/pwned", tags=["pwned"])


class PasswordCheckRequest(BaseModel):
    password: str = Field(..., min_length=1, description="Password to check")


@router.post("/check")
async def check_password(payload: PasswordCheckRequest) -> dict[str, Any]:
    """Return how many times a password has appeared in known breaches.

    Uses the k-anonymity SHA-1 range search, so only the first 5 hex chars of
    the password hash are sent to the Pwned Passwords API.
    """
    client = PwnedPasswordsClient()
    try:
        count = await client.check_password(payload.password)
    except PwnedPasswordsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Pwned Passwords request failed: {exc}") from exc
    return {"count": count, "breached": count > 0}
