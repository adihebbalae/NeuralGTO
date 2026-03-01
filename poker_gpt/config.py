"""
config.py — Configuration for PokerGPT.

Manages paths, API keys, solver settings, and defaults.
Uses environment variables (via .env file) for sensitive data.

Created: 2026-02-06
Updated: 2026-02-06 — Replaced OpenAI with Google Gemini

DOCUMENTATION:
- GEMINI_API_KEY: Set in .env file or environment variable
- GEMINI_MODEL: Model name (default: gemini-2.0-flash)
- SOLVER_BINARY_PATH: Path to TexasSolver console.exe (downloaded from releases)
- SOLVER_RESOURCES_PATH: Path to TexasSolver resources/ directory
- SOLVER_MODE: "holdem" or "shortdeck"
"""

import os
import platform
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ──────────────────────────────────────────────
# Platform Detection
# ──────────────────────────────────────────────
PLATFORM = platform.system()  # "Windows", "Linux", "Darwin"
IS_WINDOWS = PLATFORM == "Windows"
IS_LINUX = PLATFORM == "Linux"
IS_MAC = PLATFORM == "Darwin"

# ──────────────────────────────────────────────
# TexasSolver Auto-Download (for Streamlit Cloud / Linux)
# ──────────────────────────────────────────────
_SOLVER_RELEASE_URL = (
    "https://github.com/bupticybee/TexasSolver/releases/download/"
    "v0.2.0/TexasSolver-v0.2.0-Linux.zip"
)


def ensure_solver_binary() -> bool:
    """Download and set up the TexasSolver Linux binary if not present.

    Called on Streamlit Cloud (Linux) to auto-provision the solver on
    first run. Downloads from GitHub Releases, extracts, and sets
    execute permission.

    Returns:
        True if binary is available (downloaded or already exists), False on error.
    """
    solver_dir = _PROJECT_ROOT / "solver_bin" / "TexasSolver-v0.2.0-Linux"
    binary = solver_dir / "console_solver"
    resources = solver_dir / "resources"

    # Already set up — nothing to do
    if binary.exists() and resources.exists():
        return True

    # Only auto-download on Linux (Streamlit Cloud)
    if IS_WINDOWS:
        return False

    import io
    import stat
    import zipfile
    import urllib.request

    try:
        print("[CONFIG] Downloading TexasSolver v0.2.0 Linux binary...")
        solver_dir.mkdir(parents=True, exist_ok=True)

        # Download the release zip
        with urllib.request.urlopen(_SOLVER_RELEASE_URL, timeout=120) as resp:
            zip_data = io.BytesIO(resp.read())

        # Extract — the zip contains "TexasSolver-v0.2.0-Linux/" as root
        with zipfile.ZipFile(zip_data) as zf:
            for member in zf.namelist():
                # Skip macOS metadata (__MACOSX/) and .DS_Store
                if "__MACOSX" in member or ".DS_Store" in member:
                    continue
                # Strip the root dir prefix
                prefix = "TexasSolver-v0.2.0-Linux/"
                if member.startswith(prefix):
                    rel_path = member[len(prefix):]
                else:
                    continue
                if not rel_path:
                    continue

                target = solver_dir / rel_path
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())

        # Set execute permission on the binary
        if binary.exists():
            binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            print(f"[CONFIG] TexasSolver ready at {binary}")
            return True
        else:
            print("[CONFIG] Download completed but binary not found in archive.")
            return False

    except Exception as e:
        print(f"[CONFIG] Failed to download solver: {e}")
        return False

# ──────────────────────────────────────────────
# Google Gemini Configuration
# ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Fallback: try Streamlit secrets when running in Streamlit Cloud
if not GEMINI_API_KEY:
    try:
        import streamlit as st  # noqa: E402
        GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass  # Not running inside Streamlit, or secrets not configured
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # gemini-2.5-flash for best speed+quality
GEMINI_TEMPERATURE = 0.1  # Low temperature for deterministic parsing

# ──────────────────────────────────────────────
# TexasSolver Paths
# ──────────────────────────────────────────────
# Path to the TexasSolver console binary
# Download from: https://github.com/bupticybee/TexasSolver/releases
_SOLVER_BINARY_NAME = "console_solver.exe" if IS_WINDOWS else "console_solver"
_SOLVER_DIR_SUFFIX = "Windows" if IS_WINDOWS else "Linux" if IS_LINUX else "Mac"
SOLVER_BINARY_PATH = os.getenv(
    "SOLVER_BINARY_PATH",
    str(_PROJECT_ROOT / "solver_bin" / f"TexasSolver-v0.2.0-{_SOLVER_DIR_SUFFIX}" / _SOLVER_BINARY_NAME)
)

# Path to the TexasSolver resources directory (contains compairer data)
SOLVER_RESOURCES_PATH = os.getenv(
    "SOLVER_RESOURCES_PATH",
    str(_PROJECT_ROOT / "solver_bin" / f"TexasSolver-v0.2.0-{_SOLVER_DIR_SUFFIX}" / "resources")
)

# Solver mode: "holdem" or "shortdeck"
SOLVER_MODE = os.getenv("SOLVER_MODE", "holdem")

# ──────────────────────────────────────────────
# Solver Execution Settings
# ──────────────────────────────────────────────
SOLVER_THREAD_NUM = int(os.getenv("SOLVER_THREAD_NUM", "4"))
SOLVER_ACCURACY = float(os.getenv("SOLVER_ACCURACY", "0.5"))  # % of pot exploitability
SOLVER_MAX_ITERATIONS = int(os.getenv("SOLVER_MAX_ITERATIONS", "200"))
SOLVER_PRINT_INTERVAL = 10
SOLVER_USE_ISOMORPHISM = 1
SOLVER_ALLIN_THRESHOLD = 0.67
SOLVER_DUMP_ROUNDS = 2  # How many streets deep to dump

# Timeout for solver execution (seconds)
SOLVER_TIMEOUT = int(os.getenv("SOLVER_TIMEOUT", "300"))  # 5 minutes max

# ──────────────────────────────────────────────
# Working Directories
# ──────────────────────────────────────────────
WORK_DIR = _PROJECT_ROOT / "poker_gpt" / "_work"
SOLVER_INPUT_FILE = WORK_DIR / "solver_input.txt"
SOLVER_OUTPUT_FILE = WORK_DIR / "output_result.json"

# ──────────────────────────────────────────────
# LLM Provider Configuration
# ──────────────────────────────────────────────
# "gemini" (default, uses Gemini API) or "local" (uses Ollama or compatible endpoint)
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")

# Local LLM settings (used when LLM_PROVIDER="local")
LOCAL_LLM_ENDPOINT: str = os.getenv("LOCAL_LLM_ENDPOINT", "http://localhost:11434/api/generate")
LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:14b")

# ──────────────────────────────────────────────
# Feature Flags
# ──────────────────────────────────────────────
# If True, use solver when available; if False, always use GPT fallback
USE_SOLVER = os.getenv("USE_SOLVER", "true").lower() == "true"

# If True, print debug information during pipeline execution
DEBUG = os.getenv("POKERGPT_DEBUG", "false").lower() == "true"

# ──────────────────────────────────────────────
# Analysis Mode Presets (Fast / Default / Pro)
# ──────────────────────────────────────────────
MODE_PRESETS = {
    "fast": {
        "use_solver": False,
        "accuracy": None,
        "max_iterations": None,
        "timeout": None,
        "dump_rounds": None,
        "description": "LLM-only (~10s) — Quick GTO-approximate advice",
    },
    "default": {
        "use_solver": True,
        "accuracy": 2.0,
        "max_iterations": 100,
        "timeout": 180,
        "dump_rounds": 2,
        "description": "Solver ~98% accuracy (2% exploitability, ~1-2 min)",
    },
    "pro": {
        "use_solver": True,
        "accuracy": 0.3,
        "max_iterations": 500,
        "timeout": 600,
        "dump_rounds": 3,
        "description": "Solver ~99.7% accuracy (0.3% exploitability, ~4-6 min)",
    },
}


def validate_config():
    """Check that required configuration is present. Returns list of warnings."""
    warnings = []
    if not GEMINI_API_KEY:
        warnings.append("GEMINI_API_KEY not set. Set it in .env file or environment.")
    if USE_SOLVER and not Path(SOLVER_BINARY_PATH).exists():
        warnings.append(
            f"Solver binary not found at {SOLVER_BINARY_PATH}. "
            "Will use GPT-only fallback mode. "
            "Download from https://github.com/bupticybee/TexasSolver/releases"
        )
    if USE_SOLVER and not Path(SOLVER_RESOURCES_PATH).exists():
        warnings.append(
            f"Solver resources not found at {SOLVER_RESOURCES_PATH}. "
            "The solver needs the resources/ directory to run."
        )
    return warnings


def ensure_work_dir():
    """Create the working directory if it doesn't exist."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)


def check_env() -> bool:
    """
    Validate environment setup and print a clear status checklist.

    Checks GEMINI_API_KEY, SOLVER_BINARY_PATH, and SOLVER_RESOURCES_PATH.
    Prints a formatted checklist to stdout.

    Returns:
        True if the minimum required config (GEMINI_API_KEY) is present.
        False if the pipeline cannot function.
    """
    import sys

    issues_found = False
    lines: list[str] = []

    # --- Platform info ---
    lines.append(f"  ℹ Platform: {PLATFORM} ({platform.machine()})")
    if not IS_WINDOWS:
        lines.append(
            "  ℹ Solver note: TexasSolver Linux/Mac binaries must be downloaded "
            "separately from https://github.com/bupticybee/TexasSolver/releases"
        )

    # --- .env file existence ---
    env_file = _PROJECT_ROOT / ".env"
    if not env_file.exists():
        lines.append("  ✗ .env file not found")
        lines.append("    → Copy .env.example to .env and fill in your keys:")
        lines.append("      cp .env.example .env")
        issues_found = True

    # --- GEMINI_API_KEY ---
    if GEMINI_API_KEY and GEMINI_API_KEY != "your-gemini-api-key-here":
        if not GEMINI_API_KEY.startswith("AIza"):
            lines.append("  ⚠ GEMINI_API_KEY: set but doesn't look like a valid Gemini key (expected 'AIza...')")
        else:
            lines.append("  ✓ GEMINI_API_KEY: set")
    else:
        lines.append("  ✗ GEMINI_API_KEY: not set")
        lines.append("    → Create a .env file with: GEMINI_API_KEY=your-key-here")
        lines.append("    → Get a key at https://aistudio.google.com/apikey")
        issues_found = True

    # --- Model ---
    lines.append(f"  ℹ Model: {GEMINI_MODEL}")

    # --- SOLVER_BINARY_PATH ---
    solver_path = Path(SOLVER_BINARY_PATH)
    if solver_path.exists():
        lines.append(f"  ✓ SOLVER_BINARY_PATH: found")
    else:
        lines.append(f"  ✗ SOLVER_BINARY_PATH: not found at {SOLVER_BINARY_PATH}")
        lines.append("    → Download from https://github.com/bupticybee/TexasSolver/releases")
        lines.append("    → Solver is optional — pipeline falls back to LLM-only mode")

    # --- SOLVER_RESOURCES_PATH ---
    resources_path = Path(SOLVER_RESOURCES_PATH)
    if resources_path.exists():
        lines.append(f"  ✓ SOLVER_RESOURCES_PATH: found")
    else:
        lines.append(f"  ✗ SOLVER_RESOURCES_PATH: not found at {SOLVER_RESOURCES_PATH}")
        lines.append("    → Should be in the same directory as the solver binary")

    # Only print if there are issues
    if issues_found or not solver_path.exists() or not resources_path.exists():
        print("\n⚠ NeuralGTO Setup Check:")
        for line in lines:
            print(line)
        print()

    if issues_found:
        return False
    return True
