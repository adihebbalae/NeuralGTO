"""
history.py — Query logging and history for NeuralGTO.

Persists every analysis query to a local JSONL file so users can
review past hands, track study patterns, and export data for
research analysis.

Created: 2026-02-27

DOCUMENTATION:
    History is stored at ``~/.neuralgto/history.jsonl`` (one JSON object
    per line).  The directory is created automatically on first write.

    The file is capped at ``_MAX_HISTORY_ENTRIES`` (default 500) to
    prevent unbounded disk growth.  When the cap is exceeded, the oldest
    entries are pruned on the next write.

    Functions:
        log_query()       — append a single analysis result
        get_history()     — read the last *N* entries
        get_history_path() — return the Path to the history file
        clear_history()   — delete all entries, return count cleared

    The module never raises on write failures; errors are swallowed
    and logged only when ``config.DEBUG`` is True.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from poker_gpt import config


# ──────────────────────────────────────────────
# History file location & limits
# ──────────────────────────────────────────────
_HISTORY_DIR = Path.home() / ".neuralgto"
_HISTORY_FILE = _HISTORY_DIR / "history.jsonl"
_MAX_HISTORY_ENTRIES: int = int(os.getenv("NEURALGTO_MAX_HISTORY_ENTRIES", "500"))


def get_history_path() -> Path:
    """Return the path to the history JSONL file.

    Returns:
        Path object pointing to ``~/.neuralgto/history.jsonl``.
    """
    return _HISTORY_FILE


def _ensure_history_dir() -> None:
    """Create ``~/.neuralgto/`` if it does not already exist."""
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def log_query(
    result: dict,
    query: str,
    opponent_notes: str = "",
) -> None:
    """Append one analysis entry to the history file.

    Extracts relevant fields from the pipeline *result* dict and the
    original *query* string, then writes a single JSON line.

    Args:
        result: The dict returned by ``analyze_hand()``.
        query: The user's original natural-language input.
        opponent_notes: Optional villain tendency description.
    """
    try:
        scenario = result.get("scenario")
        strategy = result.get("strategy")

        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "mode": result.get("mode", ""),
            "source": result.get("source", ""),
            "confidence": result.get("confidence", ""),
            "hero_hand": getattr(scenario, "hero_hand", "") if scenario else "",
            "hero_position": getattr(scenario, "hero_position", "") if scenario else "",
            "board": getattr(scenario, "board", "") if scenario else "",
            "best_action": getattr(strategy, "best_action", "") if strategy else "",
            "best_action_freq": (
                round(strategy.best_action_freq, 4)
                if strategy and hasattr(strategy, "best_action_freq")
                else None
            ),
            "solve_time": round(result.get("solve_time", 0.0), 2),
            "opponent_notes": opponent_notes,
        }

        _ensure_history_dir()
        with open(_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Prevent unbounded growth: truncate to last _MAX_HISTORY_ENTRIES
        _truncate_history_if_needed()
    except Exception as exc:
        if config.DEBUG:
            print(f"[history] Failed to log query: {exc}")


def _truncate_history_if_needed() -> None:
    """Truncate history file to ``_MAX_HISTORY_ENTRIES`` most-recent entries.

    Called after every write.  Reads the file, keeps only the tail,
    and rewrites atomically.  Silently swallows errors.
    """
    try:
        if not _HISTORY_FILE.exists():
            return
        lines = _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _MAX_HISTORY_ENTRIES:
            return
        # Keep the most recent entries
        trimmed = lines[-_MAX_HISTORY_ENTRIES:]
        _HISTORY_FILE.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
        if config.DEBUG:
            print(
                f"[history] Truncated {len(lines)} → {len(trimmed)} entries"
            )
    except Exception:
        pass  # never crash on housekeeping


def get_history(limit: int = 50) -> list[dict]:
    """Read the last *limit* entries from the history file.

    Args:
        limit: Maximum number of entries to return (default 50).

    Returns:
        A list of dicts (most-recent last) with at most *limit* items.
        Returns an empty list if the file does not exist or is unreadable.
    """
    if not _HISTORY_FILE.exists():
        return []

    try:
        entries: list[dict] = []
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # skip malformed lines
        return entries[-limit:]
    except Exception as exc:
        if config.DEBUG:
            print(f"[history] Failed to read history: {exc}")
        return []


def clear_history() -> int:
    """Delete all history entries.

    Returns:
        The number of entries that were cleared, or 0 if the file did
        not exist.
    """
    if not _HISTORY_FILE.exists():
        return 0

    try:
        count = 0
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        _HISTORY_FILE.unlink()
        return count
    except Exception as exc:
        if config.DEBUG:
            print(f"[history] Failed to clear history: {exc}")
        return 0
