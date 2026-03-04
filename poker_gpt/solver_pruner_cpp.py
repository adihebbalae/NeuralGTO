"""
solver_pruner_cpp.py — Python interface to C++ pruning module (T4.2c).

Provides fast C++ implementation of performance-critical solver operations.
Falls back to pure Python if C++ module fails to load.

Created: 2026-03-03
Task: T4.2c

DOCUMENTATION:
- Wraps solver_pruner_cpp C++ module (pybind11)
- All functions have same signatures as solver_harness.py equivalents
- Transparent fallback to Python when C++ unavailable
- No external API calls (CPU-only operations)
"""

from pathlib import Path
from typing import Optional

from poker_gpt import config

# Attempt to import C++ module
_cpp_available = False
try:
    from . import _solver_pruner_cpp as _cpp
    _cpp_available = True
    if config.DEBUG:
        print("[SOLVER_PRUNER_CPP] C++ module loaded successfully")
except ImportError as e:
    if config.DEBUG:
        print(f"[SOLVER_PRUNER_CPP] C++ module not available, using Python fallback: {e}")
    _cpp = None


def is_cpp_available() -> bool:
    """Check if the C++ pruning module is available.
    
    Returns:
        True if C++ module loaded successfully, False otherwise.
    """
    return _cpp_available


def extract_action_frequencies_cpp(json_path: Path) -> Optional[dict[str, float]]:
    """
    Extract action frequencies from solver JSON (C++ implementation).
    
    Args:
        json_path: Path to the solver output JSON file.
        
    Returns:
        Dict mapping action names to average frequencies, or None on failure.
    """
    if not _cpp_available:
        return None
        
    try:
        result = _cpp.extract_action_frequencies(str(json_path))
        return dict(result)  # Convert C++ map to Python dict
    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_PRUNER_CPP] C++ extraction failed: {e}")
        return None


def normalize_action_names_cpp(
    frequencies: dict[str, float],
    pot_size_bb: float,
    effective_stack_bb: float,
    bet_sizes_pct: list[int] | None = None,
) -> Optional[dict[str, float]]:
    """
    Normalize action names from chip amounts to percentages (C++ implementation).
    
    Args:
        frequencies: Dict of raw action names to frequencies.
        pot_size_bb: Pot size in big blinds.
        effective_stack_bb: Effective stack in big blinds.
        bet_sizes_pct: List of configured bet size percentages (e.g., [33, 75]).
        
    Returns:
        Dict of normalized action names to frequencies, or None on failure.
    """
    if not _cpp_available:
        return None
        
    if bet_sizes_pct is None:
        bet_sizes_pct = []
        
    try:
        result = _cpp.normalize_action_names(
            frequencies,
            pot_size_bb,
            effective_stack_bb,
            bet_sizes_pct
        )
        return dict(result)
    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_PRUNER_CPP] C++ normalization failed: {e}")
        return None


def check_convergence_cpp(
    frequencies: dict[str, float],
    threshold: float = 0.01,
) -> Optional[bool]:
    """
    Check if action frequencies have converged (C++ implementation).
    
    Args:
        frequencies: Dict of action names to frequencies.
        threshold: Convergence threshold (default: 1% = 0.01).
        
    Returns:
        True if converged, False otherwise, or None on failure.
    """
    if not _cpp_available:
        return None
        
    try:
        return _cpp.check_convergence(frequencies, threshold)
    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_PRUNER_CPP] C++ convergence check failed: {e}")
        return None


def extract_and_normalize_cpp(
    json_path: Path,
    pot_size_bb: float,
    effective_stack_bb: float,
    bet_sizes_pct: list[int] | None = None,
) -> Optional[dict[str, float]]:
    """
    Extract and normalize action frequencies in one call (C++ implementation).
    
    Convenience function that combines extraction and normalization for efficiency.
    
    Args:
        json_path: Path to solver output JSON.
        pot_size_bb: Pot size in big blinds.
        effective_stack_bb: Effective stack in big blinds.
        bet_sizes_pct: List of bet size percentages.
        
    Returns:
        Dict of normalized action names to frequencies, or None on failure.
    """
    if not _cpp_available:
        return None
        
    if bet_sizes_pct is None:
        bet_sizes_pct = []
        
    try:
        result = _cpp.extract_and_normalize(
            str(json_path),
            pot_size_bb,
            effective_stack_bb,
            bet_sizes_pct
        )
        return dict(result)
    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_PRUNER_CPP] C++ extract_and_normalize failed: {e}")
        return None
