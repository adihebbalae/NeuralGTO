"""
backend/app/main.py — FastAPI application entry point.

Configures the ASGI application with lifespan management, CORS middleware,
and a health-check endpoint.  All pipeline endpoints will be registered
via routers in ``app/api/``.

Created: 2026-03-03

DOCUMENTATION:
    Run the dev server from the ``backend/`` directory::

        poetry run uvicorn app.main:app --reload --port 8000

    Or from the repo root::

        poetry run --directory backend uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.analyze import router as analyze_router
from app.config import settings
from app.models.schemas import HealthResponse


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown hooks)
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: ensure work directory exists.  Shutdown: no-op."""
    settings.ensure_work_dir()
    yield


# ──────────────────────────────────────────────
# Rate limiter (slowapi)
# ──────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)


# ──────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────

app = FastAPI(
    title="NeuralGTO API",
    description="Neuro-symbolic GTO poker advisor — FastAPI backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

# Trust the X-Forwarded-For / X-Real-IP headers from localhost only
# (nginx or cloudflared tunnel sits on 127.0.0.1).
# Without this, get_remote_address always returns 127.0.0.1 and the
# per-IP rate limit collapses to a single shared bucket for all users.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1"])


# ──────────────────────────────────────────────
# Routers
# ──────────────────────────────────────────────

app.include_router(analyze_router)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again in a minute."},
    )


# ──────────────────────────────────────────────
# CORS — whitelist only known frontends
# Origins are loaded from settings (env var ALLOWED_ORIGINS), which
# defaults to localhost dev + https://neuralgto.pages.dev.
# ──────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    # Wildcard not permitted with allow_credentials=True (browser spec);
    # enumerate the headers the frontend actually sends.
    allow_headers=["Content-Type"],
)


# ──────────────────────────────────────────────
# Stub endpoint: GET /api/health
# ──────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness / readiness check.

    Returns:
        HealthResponse with status, solver availability, and version.
    """
    return HealthResponse(
        status="ok",
        solver_available=False,   # Solver integration in a later task
        version="0.1.0",
    )
