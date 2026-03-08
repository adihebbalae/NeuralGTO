"""
backend/app/config.py — Centralised configuration for the FastAPI backend.

All environment variables, mode presets, and runtime settings are loaded here.
Endpoint code imports from this module — never reads env vars directly.

Created: 2026-03-03

DOCUMENTATION:
    Environment variables (loaded from .env via python-dotenv):
        GEMINI_API_KEY        — Google Gemini API key (required for analysis)
        NEURALGTO_DEBUG       — "1" to enable verbose logging
        NEURALGTO_SOLVER_TIMEOUT — Solver subprocess timeout in seconds (default 90)

    Usage in endpoint code::

        from app.config import settings
        key = settings.GEMINI_API_KEY
        timeout = settings.SOLVER_TIMEOUT
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ──────────────────────────────────────────────
# Load .env from project root (two levels up from this file)
# ──────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_FILE)


# ──────────────────────────────────────────────
# Mode presets (mirrors poker_gpt/config.py)
# ──────────────────────────────────────────────

MODE_PRESETS: dict[str, dict] = {
    "fast": {
        "use_solver": False,
        "max_iterations": 0,
        "accuracy": 0,
        "timeout": 0,
        "description": "LLM-only — no solver, instant response.",
    },
    "default": {
        "use_solver": True,
        "max_iterations": 100,
        "accuracy": 0.02,
        "timeout": 120,
        "description": "Solver with 100 iterations, 2% accuracy.",
    },
    "pro": {
        "use_solver": True,
        "max_iterations": 500,
        "accuracy": 0.003,
        "timeout": 360,
        "description": "Solver with 500 iterations, 0.3% accuracy.",
    },
}


# ──────────────────────────────────────────────
# Settings singleton
# ──────────────────────────────────────────────

class _Settings:
    """Read-once settings object.  Attributes are populated from env vars."""

    __slots__ = (
        "ALLOWED_ORIGINS",
        "GEMINI_API_KEY",
        "DEBUG",
        "SOLVER_TIMEOUT",
        "PROJECT_ROOT",
        "WORK_DIR",
    )

    def __init__(self) -> None:
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        self.DEBUG: bool = os.getenv("NEURALGTO_DEBUG", "") == "1"
        self.SOLVER_TIMEOUT: int = int(
            os.getenv("NEURALGTO_SOLVER_TIMEOUT", "90")
        )
        self.PROJECT_ROOT: Path = _PROJECT_ROOT
        self.WORK_DIR: Path = _PROJECT_ROOT / "_work"
        # Comma-separated allowed CORS origins from env (defaults cover local
        # dev + Cloudflare Pages production + Cloudflare tunnel).
        _raw_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:4173,https://neuralgto.pages.dev,https://api.neuralgto.pages.dev",
        )
        self.ALLOWED_ORIGINS: list[str] = [
            o.strip() for o in _raw_origins.split(",") if o.strip()
        ]

    def ensure_work_dir(self) -> None:
        """Create the work directory if it doesn't exist."""
        self.WORK_DIR.mkdir(parents=True, exist_ok=True)


settings = _Settings()
