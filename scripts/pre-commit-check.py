#!/usr/bin/env python3
"""
scripts/pre-commit-check.py — NeuralGTO security pre-commit validator.

Checks staged changes for:
  1. Hardcoded API keys / credentials
  2. Dangerous builtins (eval, exec) and shell injection (subprocess shell flag) in Python files
  3. Forbidden files staged (.env, _priv/, _dev/, .github/, solver_bin/)

Usage:
  Called automatically by .git/hooks/pre-commit.
  Can also be run manually: python scripts/pre-commit-check.py

Exit codes:
  0 — all checks passed, commit allowed
  1 — violations found, commit blocked
"""

import re
import subprocess
import sys

# ── ANSI colours ─────────────────────────────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Secret / credential patterns ─────────────────────────────────────────────
# Each entry: (regex, human-readable label)
# Applied to ALL added lines in the staged diff.
SECRET_PATTERNS = [
    # Google / Gemini API key — starts with AIza, 39 chars total
    (r'AIza[0-9A-Za-z\-_]{35}', "Google/Gemini API key"),
    # OpenAI / Anthropic-style secret key
    (r'sk-[A-Za-z0-9]{20,}', "OpenAI/Anthropic-style secret key"),
    # AWS access key ID
    (r'AKIA[0-9A-Z]{16}', "AWS access key ID"),
    # Generic: identifier = "long-string-that-looks-like-a-key"
    # Catches: API_KEY = "abc123...", SECRET = 'xyz...'
    # Whitelisted below if the line reads from env/config.
    (
        r'(?i)(?:api_key|api_secret|secret_key|access_token|auth_token|password)\s*=\s*["\'][A-Za-z0-9+/=\-_\.]{20,}["\']',
        "Hardcoded credential assignment",
    ),
]

# ── Code violations (Python only) ────────────────────────────────────────────
CODE_VIOLATIONS = [
    (r'\beval\s*\(', "eval() — forbidden, use ast.literal_eval() or explicit parsing"),  # nosec
    (r'\bexec\s*\(', "exec() — forbidden, use explicit logic"),  # nosec
    (r'\bshell\s*=\s*True\b', "shell=True in subprocess — pass command as a list instead"),  # nosec
]

# ── Files / paths that must never be staged ──────────────────────────────────
# Each entry: (regex matched against staged filename, label)
FORBIDDEN_PATHS = [
    (r'^\.env$',          ".env — credentials file"),
    (r'^\.env\.',         ".env variant — credentials file"),
    (r'^_priv/',          "_priv/ — local-only private folder"),
    (r'^_dev/',           "_dev/ — local-only private folder"),
    (r'^_notes/',         "_notes/ — local-only private folder"),
    (r'^\.github/',       ".github/ — local-only agent prompts"),
    (r'^solver_bin/',     "solver_bin/ — binary files, gitignored"),
]

# ── Whitelist: lines containing these are skipped for secret checks ───────────
# Covers: reading from env vars, config module, example files, comments.
SECRET_WHITELIST = re.compile(
    r'os\.getenv|os\.environ|config\.|\.env\.example|#|getenv\(|environ\['
)
# Lines ending with this comment are skipped entirely (same convention as bandit)
NOSEC = "# nosec"

# ── Git helpers ───────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.stdout or ""


def get_staged_files() -> list[str]:
    """Return list of staged file paths (Added, Copied, Modified only)."""
    out = _run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [f.strip() for f in out.splitlines() if f.strip()]


def get_staged_diff() -> str:
    """Return the full unified diff of all staged changes."""
    return _run(["git", "diff", "--cached", "-U0"])


def parse_added_lines(diff: str) -> dict[str, list[tuple[int, str]]]:
    """
    Parse a unified diff into {filename: [(line_number, content), ...]}.
    Only captures lines being *added* (+ lines, not +++ header).
    """
    if not diff:
        return {}
    result: dict[str, list[tuple[int, str]]] = {}
    current_file: str | None = None
    current_lineno = 0

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            result.setdefault(current_file, [])
        elif line.startswith("@@ "):
            # Extract new-file start line from @@ -a,b +c,d @@ header
            m = re.search(r'\+(\d+)', line)
            if m:
                current_lineno = int(m.group(1)) - 1
        elif current_file and line.startswith("+") and not line.startswith("+++"):
            current_lineno += 1
            result[current_file].append((current_lineno, line[1:]))
        elif current_file and not line.startswith("-"):
            # Context line — advance line counter for new file
            current_lineno += 1

    return result


# ── Checks ────────────────────────────────────────────────────────────────────

def check_forbidden_paths(staged_files: list[str]) -> list[str]:
    errors: list[str] = []
    for filepath in staged_files:
        for pattern, label in FORBIDDEN_PATHS:
            if re.match(pattern, filepath):
                errors.append(
                    f"  {RED}[FORBIDDEN FILE]{RESET} {BOLD}{filepath}{RESET}\n"
                    f"    Reason: {label}\n"
                    f"    Fix:    git restore --staged {filepath!r}"
                )
    return errors


def check_secrets(added_lines: dict[str, list[tuple[int, str]]]) -> list[str]:
    errors: list[str] = []
    for filename, lines in added_lines.items():
        for lineno, content in lines:
            stripped = content.strip()
            # Skip blank lines, pure comment lines, and # nosec markers
            if not stripped or stripped.startswith("#") or stripped.endswith(NOSEC):
                continue
            # Skip lines that are clearly reading from the environment/config
            if SECRET_WHITELIST.search(content):
                continue
            for pattern, label in SECRET_PATTERNS:
                if re.search(pattern, content):
                    errors.append(
                        f"  {RED}[HARDCODED SECRET]{RESET} {BOLD}{filename}:{lineno}{RESET}  — {label}\n"
                        f"    {YELLOW}{stripped[:120]}{RESET}\n"
                        f"    Fix:    store in .env and read via config.{label.split()[0].upper()} or os.getenv()"
                    )
                    break  # one report per line
    return errors


def check_code_violations(added_lines: dict[str, list[tuple[int, str]]]) -> list[str]:
    errors: list[str] = []
    for filename, lines in added_lines.items():
        if not filename.endswith(".py"):
            continue
        for lineno, content in lines:
            stripped = content.strip()
            # Skip blank lines, comments, and # nosec markers
            if not stripped or stripped.startswith("#") or stripped.endswith(NOSEC):
                continue
            for pattern, label in CODE_VIOLATIONS:
                if re.search(pattern, content):
                    errors.append(
                        f"  {RED}[CODE VIOLATION]{RESET} {BOLD}{filename}:{lineno}{RESET}  — {label}\n"
                        f"    {YELLOW}{stripped[:120]}{RESET}"
                    )
                    break
    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    staged_files = get_staged_files()
    if not staged_files:
        # Nothing staged — let git handle the "nothing to commit" message
        return 0

    all_violations: list[str] = []

    # ── Check 1: forbidden files ──────────────────────────────────────────────
    forbidden = check_forbidden_paths(staged_files)
    if forbidden:
        all_violations.append(f"\n{CYAN}● Forbidden files staged:{RESET}")
        all_violations.extend(forbidden)

    # ── Check 2 & 3: parse diff, scan added lines ─────────────────────────────
    diff = get_staged_diff()
    added_lines = parse_added_lines(diff)

    secrets = check_secrets(added_lines)
    if secrets:
        all_violations.append(f"\n{CYAN}● Hardcoded secrets / credentials:{RESET}")
        all_violations.extend(secrets)

    code_violations = check_code_violations(added_lines)
    if code_violations:
        all_violations.append(f"\n{CYAN}● Dangerous code patterns:{RESET}")
        all_violations.extend(code_violations)

    # ── Report ────────────────────────────────────────────────────────────────
    if all_violations:
        width = 48
        print(f"\n{BOLD}{RED}╔{'═' * width}╗{RESET}")
        print(f"{BOLD}{RED}║{'  🔒 SECURITY PRE-COMMIT CHECK FAILED':^{width}}║{RESET}")
        print(f"{BOLD}{RED}║{f'  {len([v for v in all_violations if v.startswith(chr(32) + chr(32))])} violation(s) found — commit blocked':^{width}}║{RESET}")
        print(f"{BOLD}{RED}╚{'═' * width}╝{RESET}")
        for v in all_violations:
            print(v)
        print(
            f"\n{YELLOW}To force bypass (NOT recommended unless you're certain):{RESET}"
            f"\n  git commit --no-verify\n"
        )
        return 1

    print(f"{GREEN}✓ Security pre-commit checks passed ({len(staged_files)} file(s) scanned).{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
