"""IntelX routes — selector search (email/domain/IP) for the frontend."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..intelx import IntelXClient, IntelXError, IntelXInvalidSelectorError, IntelXNotConfiguredError

router = APIRouter(prefix="/api/intelx", tags=["intelx"])


@router.get("/search")
async def search_selector(
    selector: str = Query(..., description="Selector to search (email, domain, IP, ...)"),
) -> dict[str, Any]:
    """Search IntelX for a selector and return matching leak/paste records."""
    if not selector or len(selector) < 3:
        raise HTTPException(status_code=422, detail="A selector of at least 3 characters is required")
    client = IntelXClient()
    try:
        results = await client.search(selector)
    except IntelXNotConfiguredError:
        raise HTTPException(status_code=503, detail="INTELX_API_KEY is not configured") from None
    except IntelXInvalidSelectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntelXError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"IntelX request failed: {exc}") from exc
    return {"selector": selector, "results": [r.to_dict() for r in results]}
