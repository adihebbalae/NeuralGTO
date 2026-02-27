"""
auth.py — Lightweight authentication & free-tier gating for NeuralGTO.

Provides:
  - Anonymous free-tier tracking (N free analyses per session)
  - Email + password registration / login
  - Persistent user storage (JSON-based, suitable for MVP; swap for DB later)
  - Session management via Streamlit session_state

User data is stored at ``~/.neuralgto/users.json`` (local deployments) or
can be pointed at a shared path via ``NEURALGTO_USERS_FILE`` env var.

Created: 2026-02-27

DOCUMENTATION:
  Free-tier uses are tracked per Streamlit session (resets on page refresh).
  After exhausting free uses, the user must sign in or register.

  Configuration (env vars):
    NEURALGTO_FREE_USES       — free analyses before sign-in required (default: 1)
    NEURALGTO_USERS_FILE      — path to users JSON file
    NEURALGTO_MAX_USER_DAILY  — max daily requests per authenticated user (default: 50)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from poker_gpt import config

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
FREE_USES_PER_SESSION: int = int(os.getenv("NEURALGTO_FREE_USES", "1"))
MAX_USER_DAILY_REQUESTS: int = int(os.getenv("NEURALGTO_MAX_USER_DAILY", "50"))

_STORAGE_DIR = Path.home() / ".neuralgto"
_USERS_FILE = Path(
    os.getenv("NEURALGTO_USERS_FILE", str(_STORAGE_DIR / "users.json"))
)

_lock = threading.Lock()


# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────
@dataclass
class User:
    """Registered NeuralGTO user."""

    email: str
    password_hash: str  # SHA-256(salt + password)
    salt: str
    created_at: float = field(default_factory=time.time)
    total_queries: int = 0
    # Daily usage: {"YYYY-MM-DD": count}
    daily_usage: dict[str, int] = field(default_factory=dict)


# ──────────────────────────────────────────────
# Password utilities (stdlib only — no bcrypt dep)
# ──────────────────────────────────────────────
def _hash_password(password: str, salt: str) -> str:
    """SHA-256 hash of salt + password.

    Args:
        password: Plaintext password.
        salt: Random hex salt.

    Returns:
        Hex digest string.
    """
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _generate_salt() -> str:
    """Return a random 32-char hex salt."""
    return secrets.token_hex(16)


# ──────────────────────────────────────────────
# User DB (JSON file-backed)
# ──────────────────────────────────────────────
def _read_users() -> dict[str, dict]:
    """Load user database from disk.

    Returns:
        ``{email: user_dict, ...}``
    """
    try:
        if _USERS_FILE.exists():
            data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        if config.DEBUG:
            import traceback
            traceback.print_exc()
    return {}


def _write_users(data: dict[str, dict]) -> None:
    """Persist user database to disk."""
    try:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _USERS_FILE.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        if config.DEBUG:
            import traceback
            traceback.print_exc()


def _user_from_dict(d: dict) -> User:
    """Convert a stored dict back into a ``User`` dataclass."""
    return User(
        email=d["email"],
        password_hash=d["password_hash"],
        salt=d["salt"],
        created_at=d.get("created_at", 0.0),
        total_queries=d.get("total_queries", 0),
        daily_usage=d.get("daily_usage", {}),
    )


# ──────────────────────────────────────────────
# Validation helpers
# ──────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_email(email: str) -> tuple[bool, str]:
    """Basic email format validation.

    Returns:
        ``(valid, error_message)``
    """
    email = email.strip().lower()
    if not email:
        return False, "Email is required."
    if len(email) > 254:
        return False, "Email address is too long."
    if not _EMAIL_RE.match(email):
        return False, "Invalid email format."
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """Basic password strength validation.

    Returns:
        ``(valid, error_message)``
    """
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if len(password) > 128:
        return False, "Password is too long."
    return True, ""


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def register(email: str, password: str) -> tuple[bool, str]:
    """Register a new user.

    Args:
        email: User's email address.
        password: Plaintext password (will be hashed).

    Returns:
        ``(success, message)``
    """
    email = email.strip().lower()

    # Validate
    ok, err = validate_email(email)
    if not ok:
        return False, err
    ok, err = validate_password(password)
    if not ok:
        return False, err

    with _lock:
        users = _read_users()
        if email in users:
            return False, "An account with this email already exists."

        salt = _generate_salt()
        user = User(
            email=email,
            password_hash=_hash_password(password, salt),
            salt=salt,
        )
        users[email] = asdict(user)
        _write_users(users)

    return True, "Account created successfully! You can now sign in."


def login(email: str, password: str) -> tuple[bool, str]:
    """Authenticate a user.

    Args:
        email: User's email address.
        password: Plaintext password to verify.

    Returns:
        ``(success, message)``
    """
    email = email.strip().lower()

    with _lock:
        users = _read_users()
        if email not in users:
            return False, "No account found with this email."

        user_data = users[email]
        salt = user_data["salt"]
        expected_hash = user_data["password_hash"]

        if _hash_password(password, salt) != expected_hash:
            return False, "Incorrect password."

    return True, "Signed in successfully!"


def record_user_usage(email: str) -> None:
    """Increment the daily and total query count for a user.

    Args:
        email: Authenticated user's email.
    """
    email = email.strip().lower()
    today = time.strftime("%Y-%m-%d", time.localtime())

    with _lock:
        users = _read_users()
        if email not in users:
            return

        user_data = users[email]
        user_data["total_queries"] = user_data.get("total_queries", 0) + 1
        daily = user_data.get("daily_usage", {})

        # Prune entries older than 30 days
        cutoff = time.strftime(
            "%Y-%m-%d", time.localtime(time.time() - 30 * 86400)
        )
        daily = {k: v for k, v in daily.items() if k >= cutoff}

        daily[today] = daily.get(today, 0) + 1
        user_data["daily_usage"] = daily
        _write_users(users)


def check_user_daily_limit(email: str) -> tuple[bool, int]:
    """Check whether a user has remaining daily requests.

    Args:
        email: Authenticated user's email.

    Returns:
        ``(within_limit, remaining)``
    """
    email = email.strip().lower()
    today = time.strftime("%Y-%m-%d", time.localtime())

    with _lock:
        users = _read_users()
        if email not in users:
            return True, MAX_USER_DAILY_REQUESTS

        user_data = users[email]
        daily = user_data.get("daily_usage", {})
        count = daily.get(today, 0)
        remaining = max(MAX_USER_DAILY_REQUESTS - count, 0)

        return count < MAX_USER_DAILY_REQUESTS, remaining


def get_user_stats(email: str) -> dict:
    """Get usage statistics for a user.

    Args:
        email: User's email.

    Returns:
        Dict with ``total_queries``, ``today_queries``, ``member_since``.
    """
    email = email.strip().lower()
    today = time.strftime("%Y-%m-%d", time.localtime())

    with _lock:
        users = _read_users()
        if email not in users:
            return {"total_queries": 0, "today_queries": 0, "member_since": "N/A"}

        user_data = users[email]
        daily = user_data.get("daily_usage", {})
        return {
            "total_queries": user_data.get("total_queries", 0),
            "today_queries": daily.get(today, 0),
            "member_since": time.strftime(
                "%Y-%m-%d",
                time.localtime(user_data.get("created_at", 0)),
            ),
        }


# ──────────────────────────────────────────────
# Free-tier gating (session-based)
# ──────────────────────────────────────────────
def check_free_tier(session_uses: int) -> tuple[bool, int]:
    """Check whether a session still has free uses remaining.

    Args:
        session_uses: Number of analyses already performed in this session.

    Returns:
        ``(allowed, remaining)`` — *allowed* is True if user can still use
        the free tier without signing in.
    """
    remaining = max(FREE_USES_PER_SESSION - session_uses, 0)
    return session_uses < FREE_USES_PER_SESSION, remaining
