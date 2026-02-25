"""
cache.py — Solver Result Caching.

Caches solver output JSON files keyed by a hash of the solver input commands.
This avoids re-running expensive solver computations for identical or
previously-seen spots.

Cache key = SHA-256 hash of solver input commands (excluding output path).
Cache storage = poker_gpt/_cache/{hash}.json

Created: 2026-02-06

DOCUMENTATION:
- compute_cache_key(): Hash solver input file to get a 16-char hex key
- cache_lookup(): Check if we have a cached result for that key
- cache_store(): Save a solver output JSON to the cache
- get_cache_stats(): Return entry count and total size
- clear_cache(): Delete all cached entries
"""

import hashlib
import json
import shutil
import time
from pathlib import Path

from poker_gpt import config


CACHE_DIR = config._PROJECT_ROOT / "poker_gpt" / "_cache"


def compute_cache_key(input_file: Path) -> str:
    """
    Compute a cache key from solver input file contents.

    Excludes the dump_result line (contains absolute paths that vary by machine)
    so the same poker spot always maps to the same key.
    """
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Keep only solver-relevant commands (exclude dump_result with absolute path)
    relevant = [
        l.strip() for l in lines
        if l.strip() and not l.strip().startswith("dump_result")
    ]
    content = "\n".join(relevant)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def cache_lookup(cache_key: str) -> Path | None:
    """
    Check if a cached solver result exists for the given key.

    Returns:
        Path to cached JSON file if found, None otherwise.
    """
    cached_file = CACHE_DIR / f"{cache_key}.json"
    if cached_file.exists() and cached_file.stat().st_size > 0:
        if config.DEBUG:
            print(f"[CACHE] Hit: {cache_key}")
        return cached_file
    return None


def cache_store(cache_key: str, output_file: Path) -> Path:
    """
    Store a solver output JSON in the cache.

    Returns:
        Path to the cached file.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"{cache_key}.json"
    shutil.copy2(output_file, dest)

    # Store metadata for cache management
    meta = {
        "cache_key": cache_key,
        "timestamp": time.time(),
        "source_size_bytes": output_file.stat().st_size,
    }
    meta_file = CACHE_DIR / f"{cache_key}.meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    if config.DEBUG:
        size_kb = output_file.stat().st_size / 1024
        print(f"[CACHE] Stored: {cache_key} ({size_kb:.0f} KB)")

    return dest


def get_cache_stats() -> dict:
    """Return cache entry count and total size in MB."""
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_mb": 0.0}

    all_files = [f for f in CACHE_DIR.iterdir() if f.is_file()]
    data_files = [f for f in all_files if f.suffix == ".json" and not f.name.endswith(".meta.json")]
    total_size = sum(f.stat().st_size for f in all_files)

    return {
        "entries": len(data_files),
        "size_mb": round(total_size / 1024 / 1024, 1),
    }


def clear_cache() -> int:
    """Clear all cached results. Returns number of entries cleared."""
    if not CACHE_DIR.exists():
        return 0

    data_files = [
        f for f in CACHE_DIR.glob("*.json")
        if not f.name.endswith(".meta.json")
    ]
    count = len(data_files)

    shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    return count
