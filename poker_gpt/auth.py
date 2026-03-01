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
import hmac
import json
import os
import re
import secrets
import socket
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from poker_gpt import config

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
FREE_USES_PER_SESSION: int = int(os.getenv("NEURALGTO_FREE_USES", "1"))
MAX_USER_DAILY_REQUESTS: int = int(os.getenv("NEURALGTO_MAX_USER_DAILY", "5"))
# Set to "0" in tests/CI to skip DNS lookups during email validation
EMAIL_DNS_CHECK: bool = os.getenv("NEURALGTO_EMAIL_DNS_CHECK", "1") not in ("0", "false", "no")

_STORAGE_DIR = Path.home() / ".neuralgto"
_USERS_FILE = Path(
    os.getenv("NEURALGTO_USERS_FILE", str(_STORAGE_DIR / "users.json"))
)

_lock = threading.Lock()

# ──────────────────────────────────────────────
# Brute-force / registration-spam protection
# ──────────────────────────────────────────────
MAX_LOGIN_ATTEMPTS: int = int(os.getenv("NEURALGTO_MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS: int = int(os.getenv("NEURALGTO_LOGIN_LOCKOUT_SECONDS", "900"))  # 15 min
MAX_REGISTRATIONS_PER_IP: int = int(os.getenv("NEURALGTO_MAX_REGISTRATIONS_PER_IP", "3"))
REGISTRATION_WINDOW_SECONDS: int = 3600  # 1 hour

# ip → list of failed-login timestamps
_failed_logins: dict[str, list[float]] = defaultdict(list)
# ip → list of registration timestamps
_registration_timestamps: dict[str, list[float]] = defaultdict(list)


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


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks.

    Uses ``hmac.compare_digest`` which does not short-circuit,
    preventing an attacker from inferring password hash length
    or content via response-time analysis.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


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

# Disposable / temporary email domains (Layer 1).
# These services hand out throwaway addresses to bypass sign-up walls.
# Maintained as a frozen set for O(1) lookup.
_DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    # High-traffic disposable services
    "guerrillamail.com", "guerrillamail.de", "guerrillamail.net",
    "guerrillamail.org", "guerrillamailblock.com",
    "tempmail.com", "temp-mail.org", "temp-mail.io",
    "throwaway.email", "throwaway.com",
    "mailinator.com", "mailinator2.com", "streetwisemail.com",
    "maildrop.cc",
    "yopmail.com", "yopmail.fr", "yopmail.net",
    "sharklasers.com", "grr.la", "guerrillamail.info",
    "10minutemail.com", "10minutemail.net", "10minmail.com",
    "tempail.com", "tempmailaddress.com",
    "dispostable.com",
    "trashmail.com", "trashmail.me", "trashmail.net",
    "trashmail.org", "trashmail.io",
    "fakeinbox.com", "fakemail.net",
    "mohmal.com",
    "mailnesia.com",
    "mytemp.email",
    "nada.email", "nada.ltd",
    "getnada.com",
    "emailondeck.com",
    "crazymailing.com",
    "tempinbox.com",
    "mintemail.com",
    "mailcatch.com",
    "meltmail.com",
    "harakirimail.com",
    "spamgourmet.com",
    "mailnull.com",
    "discard.email",
    "discardmail.com",
    "discardmail.de",
    "33mail.com",
    "inboxalias.com",
    "jetable.org",
    "anonaddy.com",
    # Catch-all patterns for known temp-mail farms
    "mailsac.com",
    "burnermail.io",
    "tempmailo.com",
    "emailfake.com",
    "emkei.cz",
})


def _is_disposable_domain(domain: str) -> bool:
    """Check whether an email domain is a known disposable service.

    Args:
        domain: Lowercase domain portion of an email address.

    Returns:
        True if the domain is in the disposable blocklist.
    """
    return domain in _DISPOSABLE_DOMAINS


def _has_valid_mx(domain: str, timeout: float = 3.0) -> bool:
    """Verify a domain has DNS records capable of receiving email (Layer 2).

    Attempts an MX lookup via ``dns.resolver`` if available (the
    ``dnspython`` package), then falls back to a plain A-record check
    via ``socket.getaddrinfo``.  Either succeeding proves the domain is
    routable and *could* receive mail.

    Args:
        domain: Lowercase domain to check.
        timeout: Maximum seconds to wait for DNS resolution.

    Returns:
        True if the domain resolves (MX or A record found).
    """
    # Try dnspython first (richer check, optional dependency)
    try:
        import dns.resolver  # type: ignore[import-untyped]
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        try:
            answers = resolver.resolve(domain, "MX")
            return len(answers) > 0
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers):
            pass
        # Fallback: some domains route mail via A record without MX
        try:
            answers = resolver.resolve(domain, "A")
            return len(answers) > 0
        except Exception:
            return False
    except ImportError:
        pass

    # Stdlib fallback: socket.getaddrinfo (resolves A/AAAA)
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            results = socket.getaddrinfo(domain, 25, proto=socket.IPPROTO_TCP)
            return len(results) > 0
        except (socket.gaierror, socket.timeout, OSError):
            # One more attempt on port 80 (some valid domains block 25)
            try:
                results = socket.getaddrinfo(domain, 80, proto=socket.IPPROTO_TCP)
                return len(results) > 0
            except (socket.gaierror, socket.timeout, OSError):
                return False
        finally:
            socket.setdefaulttimeout(old_timeout)
    except Exception:
        return False


def validate_email(email: str, check_dns: bool = True) -> tuple[bool, str]:
    """Validate email format, domain reputation, and DNS deliverability.

    Performs three checks in order:
      1. RFC-ish format regex
      2. Disposable domain blocklist
      3. DNS MX/A record resolution (can be skipped via *check_dns=False*
         for fast unit tests)

    Args:
        email: Email address to validate.
        check_dns: When False, skip the DNS lookup (useful in tests).

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

    # Extract domain
    domain = email.rsplit("@", 1)[-1]

    # Layer 1: disposable email blocklist
    if _is_disposable_domain(domain):
        return False, "Disposable email addresses are not allowed. Please use a permanent email."

    # Layer 2: DNS deliverability
    if check_dns and not _has_valid_mx(domain):
        return False, f"Email domain '{domain}' does not appear to accept email. Please check for typos."

    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """Password strength validation.

    Requires at least 8 characters, one letter, and one digit.

    Returns:
        ``(valid, error_message)``
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if len(password) > 128:
        return False, "Password is too long."
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    return True, ""


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def check_login_lockout(client_ip: str) -> tuple[bool, int]:
    """Check whether an IP is locked out from login attempts.

    Args:
        client_ip: Client IP address.

    Returns:
        ``(allowed, seconds_remaining)`` — *allowed* is False if locked out.
    """
    now = time.time()
    cutoff = now - LOGIN_LOCKOUT_SECONDS

    with _lock:
        attempts = _failed_logins.get(client_ip, [])
        # Keep only recent attempts
        recent = [t for t in attempts if t > cutoff]
        _failed_logins[client_ip] = recent

        if len(recent) >= MAX_LOGIN_ATTEMPTS:
            oldest = min(recent)
            wait = int(oldest + LOGIN_LOCKOUT_SECONDS - now) + 1
            return False, wait

    return True, 0


def record_failed_login(client_ip: str) -> None:
    """Record a failed login attempt for brute-force tracking."""
    now = time.time()
    with _lock:
        _failed_logins[client_ip].append(now)
        # Cap list size to prevent memory growth
        if len(_failed_logins[client_ip]) > MAX_LOGIN_ATTEMPTS * 2:
            _failed_logins[client_ip] = _failed_logins[client_ip][-MAX_LOGIN_ATTEMPTS:]


def clear_failed_logins(client_ip: str) -> None:
    """Clear failed login attempts after a successful login."""
    with _lock:
        _failed_logins.pop(client_ip, None)


def check_registration_rate(client_ip: str) -> tuple[bool, str]:
    """Check whether an IP has exceeded registration rate limit.

    Args:
        client_ip: Client IP address.

    Returns:
        ``(allowed, message)``
    """
    now = time.time()
    cutoff = now - REGISTRATION_WINDOW_SECONDS

    with _lock:
        timestamps = _registration_timestamps.get(client_ip, [])
        recent = [t for t in timestamps if t > cutoff]
        _registration_timestamps[client_ip] = recent

        if len(recent) >= MAX_REGISTRATIONS_PER_IP:
            return False, f"Too many accounts created. Try again later."

    return True, ""


def record_registration(client_ip: str) -> None:
    """Record a registration event for rate limiting."""
    now = time.time()
    with _lock:
        _registration_timestamps[client_ip].append(now)


def register(email: str, password: str, client_ip: str = "") -> tuple[bool, str]:
    """Register a new user.

    Args:
        email: User's email address.
        password: Plaintext password (will be hashed).
        client_ip: Client IP for registration rate limiting.

    Returns:
        ``(success, message)``
    """
    email = email.strip().lower()

    # Validate (use module-level EMAIL_DNS_CHECK by default)
    ok, err = validate_email(email, check_dns=EMAIL_DNS_CHECK)
    if not ok:
        return False, err
    ok, err = validate_password(password)
    if not ok:
        return False, err

    # Registration rate limit (prevent bot account spam)
    if client_ip:
        ok, err = check_registration_rate(client_ip)
        if not ok:
            return False, err

    with _lock:
        users = _read_users()
        if email in users:
            return False, "Unable to create account. This email may already be registered."

        salt = _generate_salt()
        user = User(
            email=email,
            password_hash=_hash_password(password, salt),
            salt=salt,
        )
        users[email] = asdict(user)
        _write_users(users)

    # Record successful registration for rate limiting
    if client_ip:
        record_registration(client_ip)

    return True, "Account created successfully! You can now sign in."


# Generic message prevents credential enumeration (T4)
_LOGIN_FAIL_MSG = "Invalid email or password."


def login(email: str, password: str, client_ip: str = "") -> tuple[bool, str]:
    """Authenticate a user.

    Uses constant-time comparison to prevent timing attacks on the
    password hash.  Returns a generic error message to prevent
    credential enumeration (attacker can't tell if email exists).

    Args:
        email: User's email address.
        password: Plaintext password to verify.
        client_ip: Client IP for brute-force lockout tracking.

    Returns:
        ``(success, message)``
    """
    email = email.strip().lower()

    # Brute-force lockout check
    if client_ip:
        ok, wait = check_login_lockout(client_ip)
        if not ok:
            return False, f"Too many login attempts. Try again in {wait // 60 + 1} minutes."

    with _lock:
        users = _read_users()
        if email not in users:
            # Hash a dummy password to make timing consistent
            # (prevents attacker from distinguishing "no account" vs "wrong password")
            _hash_password(password, "0" * 32)
            if client_ip:
                # Release lock briefly to record (we re-lock inside record_failed_login)
                pass
            # Record after releasing lock
            if client_ip:
                _failed_logins[client_ip].append(time.time())
            return False, _LOGIN_FAIL_MSG

        user_data = users[email]
        salt = user_data["salt"]
        expected_hash = user_data["password_hash"]

        if not _constant_time_compare(_hash_password(password, salt), expected_hash):
            if client_ip:
                _failed_logins[client_ip].append(time.time())
            return False, _LOGIN_FAIL_MSG

    # Success — clear failed attempts for this IP
    if client_ip:
        clear_failed_logins(client_ip)

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
