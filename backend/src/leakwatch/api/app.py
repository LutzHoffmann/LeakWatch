"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_settings
from .matches import router as matches_router
from .pwned import router as pwned_router
from .routes import router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="LeakWatch API",
        version="0.1.0",
        description="HTTP API for the LeakWatch credential leak monitor.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(pwned_router)
    app.include_router(matches_router)
    return app


app = create_app()
