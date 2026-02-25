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
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ──────────────────────────────────────────────
# Google Gemini Configuration
# ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # gemini-2.5-flash for best speed+quality
GEMINI_TEMPERATURE = 0.1  # Low temperature for deterministic parsing

# ──────────────────────────────────────────────
# TexasSolver Paths
# ──────────────────────────────────────────────
# Path to the TexasSolver console binary
# Download from: https://github.com/bupticybee/TexasSolver/releases
SOLVER_BINARY_PATH = os.getenv(
    "SOLVER_BINARY_PATH",
    str(_PROJECT_ROOT / "solver_bin" / "TexasSolver-v0.2.0-Windows" / "console_solver.exe")
)

# Path to the TexasSolver resources directory (contains compairer data)
SOLVER_RESOURCES_PATH = os.getenv(
    "SOLVER_RESOURCES_PATH",
    str(_PROJECT_ROOT / "solver_bin" / "TexasSolver-v0.2.0-Windows" / "resources")
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
        "description": "Solver low accuracy (~1-2 min) — Good GTO approximation",
    },
    "pro": {
        "use_solver": True,
        "accuracy": 0.3,
        "max_iterations": 500,
        "timeout": 600,
        "dump_rounds": 3,
        "description": "Solver high accuracy (~4-6 min) — Precise GTO solution",
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
