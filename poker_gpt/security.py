"""
security.py — Rate-limiting, input sanitization, and abuse-detection for NeuralGTO.

Provides multiple layers of protection against bots, spam, and runaway
Gemini API costs:

  1. Per-session rate limiting (default 20 req / hour)
  2. Global rate limiting across sessions (default 100 req / hour)
  3. Cooldown between consecutive requests (default 5 s)
  4. Input validation / sanitization (length, injection, gibberish)
  5. Daily budget tracking (persistent file-based counter)
  6. Suspicious-pattern / abuse detection

All public functions return tuples — they never raise.

Created: 2026-02-27

DOCUMENTATION:
  Configuration is via environment variables (see constants below).
  Persistent daily-budget state is stored in ``~/.neuralgto/daily_usage.json``.
  In-process session state lives in a module-level dict and is lost on restart,
  which is acceptable for single-process Streamlit deployments.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from poker_gpt import config

# ──────────────────────────────────────────────
# Configuration constants (overridable via env)
# ──────────────────────────────────────────────
MAX_REQUESTS_PER_SESSION: int = int(
    os.getenv("NEURALGTO_MAX_SESSION_REQUESTS", "10")
)
MAX_REQUESTS_PER_HOUR_GLOBAL: int = int(
    os.getenv("NEURALGTO_MAX_HOURLY_REQUESTS", "30")
)
MAX_REQUESTS_PER_DAY: int = int(
    os.getenv("NEURALGTO_MAX_DAILY_REQUESTS", "50")
)
REQUEST_COOLDOWN_SECONDS: int = int(
    os.getenv("NEURALGTO_COOLDOWN_SECONDS", "5")
)
MAX_INPUT_LENGTH: int = int(
    os.getenv("NEURALGTO_MAX_INPUT_LENGTH", "2000")
)

# ──────────────────────────────────────────────
# Persistent storage path
# ──────────────────────────────────────────────
_STORAGE_DIR = Path.home() / ".neuralgto"
_DAILY_USAGE_FILE = _STORAGE_DIR / "daily_usage.json"

# ──────────────────────────────────────────────
# In-memory session state (per-process)
# ──────────────────────────────────────────────
_lock = threading.Lock()

# Maximum distinct IPs/sessions tracked in memory (T6: prevent memory exhaustion)
_MAX_TRACKED_KEYS: int = 10_000

# session_id → list of timestamps
_session_timestamps: dict[str, list[float]] = defaultdict(list)

# session_id → last-request timestamp
_session_last_request: dict[str, float] = {}

# global timestamp list (all sessions)
_global_timestamps: list[float] = []

# session_id → list of recent queries (for duplicate detection)
_session_recent_queries: dict[str, list[str]] = defaultdict(list)


def _evict_stale_keys() -> None:
    """Evict oldest entries when in-memory dicts exceed ``_MAX_TRACKED_KEYS``.

    Called under ``_lock``. Removes the 20% oldest entries by last-seen
    timestamp so we don't do this on every single request.
    """
    if len(_session_timestamps) <= _MAX_TRACKED_KEYS:
        return

    # Build a last-seen timestamp per key
    last_seen: dict[str, float] = {}
    for key, ts_list in _session_timestamps.items():
        last_seen[key] = max(ts_list) if ts_list else 0.0

    # Sort by last-seen ascending → evict oldest 20%
    evict_count = len(last_seen) // 5
    to_evict = sorted(last_seen, key=last_seen.get)[:evict_count]

    for key in to_evict:
        _session_timestamps.pop(key, None)
        _session_last_request.pop(key, None)
        _session_recent_queries.pop(key, None)

# Injection / prompt-attack patterns (compiled once)
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above",
        r"disregard\s+(all\s+)?previous",
        r"you\s+are\s+now\s+(a|an|acting|pretending)",
        r"system\s*prompt",
        r"reveal\s+(your|the)\s+(system|instructions|prompt)",
        r"<\/?script",
        r"<\/?iframe",
        r"javascript\s*:",
        r"\{\{.*\}\}",           # template injection
        r"\$\{.*\}",             # template literal injection
        r"DROP\s+TABLE",
        r";\s*DELETE\s+FROM",
        r"UNION\s+SELECT",
    )
]


# ──────────────────────────────────────────────
# 1. Per-session rate limiting
# ──────────────────────────────────────────────

def check_rate_limit(
    session_id: str,
    max_requests: int = MAX_REQUESTS_PER_SESSION,
    window_seconds: int = 3600,
) -> tuple[bool, str]:
    """Check whether *session_id* has exceeded its rate limit.

    Args:
        session_id: Unique session identifier.
        max_requests: Maximum requests allowed in *window_seconds*.
        window_seconds: Sliding window size in seconds.

    Returns:
        ``(allowed, message)`` — if not allowed, *message* explains why.
    """
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        # T6: Evict stale entries if we're tracking too many IPs
        _evict_stale_keys()

        ts = _session_timestamps[session_id]
        # Prune old entries
        _session_timestamps[session_id] = ts = [t for t in ts if t > cutoff]

        if len(ts) >= max_requests:
            oldest = min(ts)
            wait = int(oldest + window_seconds - now) + 1
            return (
                False,
                f"Session rate limit reached ({max_requests} requests per "
                f"{window_seconds // 60} min). Try again in ~{wait}s.",
            )

        ts.append(now)
        return True, ""


# ──────────────────────────────────────────────
# 2. Global rate limiting
# ──────────────────────────────────────────────

def check_global_rate_limit(
    max_requests: int = MAX_REQUESTS_PER_HOUR_GLOBAL,
    window_seconds: int = 3600,
) -> tuple[bool, str]:
    """Prevent total API cost from spiraling across all sessions.

    Args:
        max_requests: Maximum total requests in *window_seconds*.
        window_seconds: Sliding window size in seconds.

    Returns:
        ``(allowed, message)``.
    """
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        global _global_timestamps
        _global_timestamps = [t for t in _global_timestamps if t > cutoff]

        if len(_global_timestamps) >= max_requests:
            return (
                False,
                f"Global rate limit reached ({max_requests} requests/hour). "
                "Please try again later.",
            )

        _global_timestamps.append(now)
        return True, ""


# ──────────────────────────────────────────────
# 3. Cooldown between requests
# ──────────────────────────────────────────────

def check_cooldown(
    session_id: str,
    cooldown_seconds: int = REQUEST_COOLDOWN_SECONDS,
) -> tuple[bool, float]:
    """Enforce a minimum gap between consecutive requests from the same session.

    Args:
        session_id: Unique session identifier.
        cooldown_seconds: Minimum seconds between requests.

    Returns:
        ``(allowed, seconds_remaining)`` — *seconds_remaining* is 0.0 when
        the request is allowed.
    """
    now = time.time()

    with _lock:
        last = _session_last_request.get(session_id, 0.0)
        elapsed = now - last

        if elapsed < cooldown_seconds:
            remaining = cooldown_seconds - elapsed
            return False, remaining

        _session_last_request[session_id] = now
        return True, 0.0


# ──────────────────────────────────────────────
# 4. Input validation / sanitization
# ──────────────────────────────────────────────

def sanitize_input(
    query: str,
    max_length: int = MAX_INPUT_LENGTH,
) -> tuple[str, list[str]]:
    """Sanitize and validate user input.

    Checks performed:
      - Strip leading/trailing whitespace
      - Collapse runs of whitespace
      - Reject inputs exceeding *max_length*
      - Detect obvious injection / prompt-attack patterns
      - Reject inputs that are just repeated characters

    Args:
        query: Raw user input.
        max_length: Maximum allowed length (after stripping).

    Returns:
        ``(cleaned_query, warnings)`` — *cleaned_query* is empty if the input
        was rejected entirely.
    """
    warnings: list[str] = []

    # Basic cleanup
    cleaned = query.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Length check
    if len(cleaned) > max_length:
        warnings.append(
            f"Input too long ({len(cleaned)} chars). Maximum is {max_length}."
        )
        return "", warnings

    # Empty after strip
    if not cleaned:
        warnings.append("Input is empty.")
        return "", warnings

    # Repeated-character spam (e.g. "aaaaaaaaaa" or "!!!!!!!!")
    if len(cleaned) > 10 and len(set(cleaned.replace(" ", ""))) <= 3:
        warnings.append("Input appears to be spam (repeated characters).")
        return "", warnings

    # Injection / prompt-attack detection
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            warnings.append("Input contains disallowed patterns.")
            if config.DEBUG:
                warnings.append(f"[debug] matched pattern: {pattern.pattern}")
            return "", warnings

    return cleaned, warnings


# ──────────────────────────────────────────────
# 5. Daily budget tracking (file-based)
# ──────────────────────────────────────────────

def _today_key() -> str:
    """Return today's date as ``YYYY-MM-DD``."""
    return time.strftime("%Y-%m-%d", time.localtime())


def _read_daily_usage() -> dict[str, int]:
    """Load daily usage counters from disk.

    Returns:
        ``{date_str: count, ...}``
    """
    try:
        if _DAILY_USAGE_FILE.exists():
            data = json.loads(_DAILY_USAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write_daily_usage(data: dict[str, int]) -> None:
    """Persist daily usage counters."""
    try:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _DAILY_USAGE_FILE.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )
    except Exception:
        if config.DEBUG:
            import traceback
            traceback.print_exc()


def check_daily_budget(
    max_daily_requests: int = MAX_REQUESTS_PER_DAY,
) -> tuple[bool, int]:
    """Check whether today's request count is within budget.

    Args:
        max_daily_requests: Maximum requests allowed per calendar day.

    Returns:
        ``(within_budget, requests_remaining)``.
    """
    today = _today_key()

    with _lock:
        usage = _read_daily_usage()
        count = usage.get(today, 0)
        remaining = max(max_daily_requests - count, 0)

        if count >= max_daily_requests:
            return False, 0

        return True, remaining


def record_daily_usage() -> None:
    """Increment today's request counter by one (call after a successful request)."""
    today = _today_key()

    with _lock:
        usage = _read_daily_usage()
        # Prune entries older than 7 days to avoid file bloat
        keys = list(usage.keys())
        for k in keys:
            if k < time.strftime(
                "%Y-%m-%d",
                time.localtime(time.time() - 7 * 86400),
            ):
                del usage[k]

        usage[today] = usage.get(today, 0) + 1
        _write_daily_usage(usage)


# ──────────────────────────────────────────────
# 6. Suspicious-pattern / abuse detection
# ──────────────────────────────────────────────

def detect_abuse(
    session_id: str,
    query: str,
) -> tuple[bool, str]:
    """Detect suspicious usage patterns.

    Heuristics:
      - Same query submitted many times (≥5 identical in last 50)
      - Extremely rapid requests (≥3 within 2 seconds)

    Args:
        session_id: Unique session identifier.
        query: The (already-sanitized) user query.

    Returns:
        ``(is_suspicious, reason)`` — ``is_suspicious`` is ``True`` if the
        request should be blocked.
    """
    now = time.time()
    normalised = query.strip().lower()

    with _lock:
        recent = _session_recent_queries[session_id]
        recent.append(normalised)
        # Keep only last 50 queries
        if len(recent) > 50:
            _session_recent_queries[session_id] = recent = recent[-50:]

        # Duplicate detection: ≥5 identical queries in recent history
        identical_count = sum(1 for q in recent if q == normalised)
        if identical_count >= 5:
            return True, "Same query repeated too many times."

        # Rapid-fire detection (check session timestamps)
        ts = _session_timestamps.get(session_id, [])
        recent_ts = [t for t in ts if now - t < 2.0]
        if len(recent_ts) >= 3:
            return True, "Requests are being sent too rapidly."

    return False, ""


# ──────────────────────────────────────────────
# 7. Anonymous (IP-based) usage tracking
# ──────────────────────────────────────────────
# Anonymous users get a small daily allowance keyed on IP.
# Persisted to disk so it survives page refreshes AND process restarts.

ANON_DAILY_LIMIT: int = int(os.getenv("NEURALGTO_ANON_DAILY_LIMIT", "3"))
_ANON_USAGE_FILE = _STORAGE_DIR / "anon_usage.json"

# In-memory cache (avoids re-reading disk every request within same process)
_anon_usage_cache: dict[str, int] = {}
_anon_usage_date: str = ""


# Basic IP format validation (IPv4, IPv6, or short fingerprint)
_IP_PATTERN = re.compile(
    r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"    # IPv4
    r"|[0-9a-fA-F:]{3,45}"                         # IPv6
    r"|fp-[0-9a-f]{16})$"                           # fingerprint fallback
)


def _sanitize_ip(raw: str) -> str | None:
    """Validate and sanitize an IP address string.

    Returns the cleaned IP if it looks valid, or None if spoofed/malformed.
    Strips whitespace and rejects strings that don't match IP patterns
    (prevents header injection via X-Forwarded-For).
    """
    cleaned = raw.strip()[:64]  # hard length cap
    if _IP_PATTERN.match(cleaned):
        return cleaned
    return None


def get_client_ip() -> str:
    """Extract client IP from Streamlit request context.

    Uses ``X-Forwarded-For`` header (set by reverse proxies on Streamlit
    Cloud, nginx, etc.) with fallbacks to ``X-Real-Ip`` and a User-Agent
    fingerprint hash for local dev.

    The extracted IP is validated against a basic format pattern to
    mitigate header-injection attacks.

    Returns:
        Client identifier string.  Never raises.
    """
    try:
        import streamlit as st  # noqa: E402 — lazy for non-Streamlit use

        headers = st.context.headers
        # X-Forwarded-For: first entry is the original client
        forwarded = headers.get("X-Forwarded-For", "")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            ip = _sanitize_ip(candidate)
            if ip:
                return ip
        real_ip = headers.get("X-Real-Ip", "")
        if real_ip:
            ip = _sanitize_ip(real_ip)
            if ip:
                return ip
        # Weak fingerprint fallback (local dev with no reverse proxy)
        ua = headers.get("User-Agent", "unknown")
        return f"fp-{hashlib.sha256(ua.encode()).hexdigest()[:16]}"
    except Exception:
        return "unknown"


def _load_anon_usage() -> dict[str, int]:
    """Load today's anonymous usage counters from disk.

    Returns:
        ``{client_ip: count, ...}`` for today, or empty dict.
    """
    today = _today_key()
    try:
        if _ANON_USAGE_FILE.exists():
            data = json.loads(_ANON_USAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("date") == today:
                return data.get("usage", {})
    except Exception:
        pass
    return {}


def _save_anon_usage(usage: dict[str, int]) -> None:
    """Persist anonymous usage counters to disk."""
    try:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _ANON_USAGE_FILE.write_text(
            json.dumps({"date": _today_key(), "usage": usage}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        if config.DEBUG:
            import traceback

            traceback.print_exc()


def check_anon_limit(client_ip: str) -> tuple[bool, int]:
    """Check whether an anonymous client has remaining free uses today.

    Tracks usage by IP address (or fingerprint), persisted to disk so it
    survives page refreshes and short process restarts.

    Args:
        client_ip: Client identifier from ``get_client_ip()``.

    Returns:
        ``(allowed, remaining)`` — *allowed* is True if under limit.
    """
    global _anon_usage_cache, _anon_usage_date
    today = _today_key()

    with _lock:
        if _anon_usage_date != today:
            _anon_usage_cache = _load_anon_usage()
            _anon_usage_date = today

        count = _anon_usage_cache.get(client_ip, 0)
        remaining = max(ANON_DAILY_LIMIT - count, 0)
        return count < ANON_DAILY_LIMIT, remaining


def record_anon_use(client_ip: str) -> None:
    """Record one anonymous usage for an IP.  Persists to disk.

    Args:
        client_ip: Client identifier from ``get_client_ip()``.
    """
    global _anon_usage_cache, _anon_usage_date
    today = _today_key()

    with _lock:
        if _anon_usage_date != today:
            _anon_usage_cache = _load_anon_usage()
            _anon_usage_date = today

        _anon_usage_cache[client_ip] = _anon_usage_cache.get(client_ip, 0) + 1
        _save_anon_usage(_anon_usage_cache)
