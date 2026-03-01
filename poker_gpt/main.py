"""
main.py — PokerGPT Entry Point & Pipeline Orchestrator.

This is the main script that runs the complete PokerGPT pipeline:
NL Input → Parse → Solver Input → Solver Run → Extract Strategy → NL Advice

Created: 2026-02-06
Updated: 2026-02-06 — Added caching, sanity checking, and 3 analysis modes

DOCUMENTATION:
Usage:
    # Interactive mode (type questions in terminal):
    python -m poker_gpt.main

    # Single query mode:
    python -m poker_gpt.main --query "I have QQ on the button..."

    # Choose analysis mode (fast / default / pro):
    python -m poker_gpt.main --mode pro --query "..."

    # With debug output:
    POKERGPT_DEBUG=true python -m poker_gpt.main

    # Force LLM-only mode (same as --mode fast):
    python -m poker_gpt.main --no-solver

Pipeline Steps:
    1. nl_parser.parse_scenario()      — NL → ScenarioData (Gemini)
   2a. cache.cache_lookup()             — Check for cached solver output
    2. solver_input.generate_solver_input()  — ScenarioData → solver_input.txt
    3. solver_runner.run_solver()       — Run TexasSolver binary
   3a. cache.cache_store()              — Cache solver output for next time
    4. strategy_extractor.extract_strategy() — Parse JSON → StrategyResult
   4a. sanity_checker.check_strategy_sanity() — LLM review of extreme frequencies
    5. nl_advisor.generate_advice()     — Strategy → NL advice (Gemini)
    
    If solver is unavailable or mode is "fast", steps 2-4 are skipped and 
    nl_advisor.generate_fallback_advice() is used instead.

Analysis Modes:
    - fast:    LLM-only (~10s)         — no solver, Gemini approximation
    - default: Solver ~98% accuracy    — 2% exploitability, 100 iterations (~1-2 min)
    - pro:     Solver ~99.7% accuracy  — 0.3% exploitability, 500 iterations (~4-6 min)

Dependencies installed:
    - google-genai (pip install google-genai)
    - python-dotenv (pip install python-dotenv)
    - streamlit (pip install streamlit)  — for web UI
"""

import argparse
import sys
import time
from typing import Callable, Optional

from poker_gpt import config
from poker_gpt.nl_parser import parse_scenario
from poker_gpt.solver_input import generate_solver_input
from poker_gpt.solver_runner import run_solver, is_solver_available
from poker_gpt.strategy_extractor import extract_strategy
from poker_gpt.nl_advisor import generate_advice, generate_fallback_advice, OUTPUT_LEVELS
from poker_gpt.sanity_checker import check_strategy_sanity
from poker_gpt.cache import compute_cache_key, cache_lookup, cache_store
from poker_gpt.preflop_lookup import lookup_preflop_strategy, is_preflop_lookup_available
from poker_gpt.validation import validate_scenario, validate_query_completeness, format_validation_errors
from poker_gpt.history import log_query, get_history
from poker_gpt.range_display import render_range_grid_rich
from poker_gpt.hand_history import (
    parse_hand_history_file,
    hand_to_query,
    hands_summary,
)
from poker_gpt.security import sanitize_input
from poker_gpt.spot_frequency import (
    get_spot_frequency,
    format_spot_frequency_for_advisor,
    SpotFrequencyInfo,
)


# ──────────────────────────────────────────────
# Confidence mapping: source → confidence label
# ──────────────────────────────────────────────
_CONFIDENCE_MAP = {
    "solver": "high",
    "solver_cached": "high",
    "preflop_lookup": "medium",
    "llm_only": "low",
    "llm_fallback": "low",
    "gpt_fallback": "low",
}

_CONFIDENCE_LABELS = {
    "high": "High \u2014 solver-verified",
    "medium": "Medium \u2014 pre-solved GTO lookup",
    "low": "Low \u2014 LLM approximation",
}

# ──────────────────────────────────────────────
# Trust Badge: visible source attribution
# ──────────────────────────────────────────────
_SOURCE_BADGES = {
    "solver": "\u2705 Powered by TexasSolver CFR engine",
    "solver_cached": "\u2705 Powered by TexasSolver CFR engine (cached)",
    "preflop_lookup": "\u2705 Based on pre-solved GTO ranges (PioSOLVER data)",
    "llm_only": "\u26a0\ufe0f LLM approximation \u2014 solver not used for this spot",
    "llm_fallback": "\u26a0\ufe0f LLM approximation \u2014 solver unavailable",
    "gpt_fallback": "\u26a0\ufe0f LLM approximation \u2014 solver unavailable",
    "validation_error": "",
}


def get_source_badge(source: str) -> str:
    """Return the trust badge string for a given source."""
    return _SOURCE_BADGES.get(source, "")


def _combine_opponent_pool_notes(opponent_notes: str, pool_notes: str) -> str:
    """Combine per-villain and pool-level tendency notes for the advisor.

    When both are provided, the advisor sees both sections so it can layer
    individual villain reads on top of population-level exploits.
    """
    parts: list[str] = []
    if opponent_notes:
        parts.append(opponent_notes)
    if pool_notes:
        parts.append(
            f"[POOL TENDENCIES — Live game prep] {pool_notes}"
        )
    return "\n\n".join(parts)


def analyze_hand(
    query: str,
    mode: str = "default",
    on_status: Optional[Callable[[str], None]] = None,
    opponent_notes: str = "",
    output_level: str = "advanced",
) -> dict:
    """
    Core analysis function — used by both CLI and web UI.
    
    Runs the full PokerGPT pipeline with caching, sanity checking,
    and mode-specific solver settings.
    
    Args:
        query: Natural language poker question.
        mode: Analysis mode — "fast", "default", or "pro".
        on_status: Optional callback for progress updates (e.g., for web UI).
        opponent_notes: Optional description of villain tendencies used to
            produce an exploitative deviation from the GTO baseline.
        output_level: "beginner" for plain-language output or "advanced"
            for the full 4-section GTO analysis. Default: "advanced".
        
    Returns:
        dict with keys: advice, mode, scenario, strategy, sanity_note,
        cached, solve_time, source, output_level.
    """
    def _status(msg: str):
        if on_status:
            try:
                on_status(msg)
            except UnicodeEncodeError:
                # Windows console can't handle some Unicode chars
                safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
                on_status(safe_msg)

    config.ensure_work_dir()
    preset = config.MODE_PRESETS.get(mode, config.MODE_PRESETS["default"])

    # ── Step 0a: Input sanitization (defense-in-depth — web_app also sanitizes) ──
    query, input_warnings = sanitize_input(query)
    if not query:
        _status(f"  \u26a0 Input rejected: {'; '.join(input_warnings)}")
        return {
            "advice": "Your input was rejected. " + " ".join(input_warnings),
            "mode": mode,
            "scenario": None,
            "strategy": None,
            "sanity_note": "",
            "cached": False,
            "solve_time": 0.0,
            "source": "validation_error",
            "confidence": "low",
            "parse_time": 0.0,
            "spot_frequency": None,
            "output_level": output_level,
        }
    if opponent_notes:
        opponent_notes, opp_warnings = sanitize_input(opponent_notes, max_length=500)
        if not opponent_notes and opp_warnings:
            _status(f"  \u26a0 Opponent notes rejected: {'; '.join(opp_warnings)}")

    # ── Step 0b: Pre-parse query validation (saves Gemini tokens) ──
    query_errors = validate_query_completeness(query)
    if query_errors:
        error_msg = format_validation_errors(
            query_errors,
            header="Your query seems incomplete — here's what's missing:",
        )
        _status(f"  ⚠ Query too vague ({len(query_errors)} issue(s)) — skipping API call")
        return {
            "advice": error_msg,
            "mode": mode,
            "scenario": None,
            "strategy": None,
            "sanity_note": "",
            "cached": False,
            "solve_time": 0.0,
            "source": "validation_error",
            "confidence": "low",
            "parse_time": 0.0,
            "spot_frequency": None,
            "output_level": output_level,
        }

    # ── Step 1: Parse natural language → structured scenario ──
    _status("Step 1/5: Parsing your poker scenario...")
    t0 = time.time()
    scenario = parse_scenario(query)
    parse_time = time.time() - t0
    _status(
        f"  ✓ Parsed in {parse_time:.1f}s — "
        f"{scenario.hero_hand} on {scenario.hero_position}, "
        f"Board: {scenario.board}"
    )

    # ── Step 1.1: Validate parsed scenario ──
    validation_errors = validate_scenario(scenario)
    if validation_errors:
        error_msg = format_validation_errors(validation_errors)
        _status(f"  ⚠ Validation issues found ({len(validation_errors)})")
        return {
            "advice": error_msg,
            "mode": mode,
            "scenario": scenario,
            "strategy": None,
            "sanity_note": "",
            "cached": False,
            "solve_time": 0.0,
            "source": "validation_error",
            "confidence": "low",
            "parse_time": parse_time,
            "spot_frequency": None,
            "output_level": output_level,
        }

    # ── Check if we should use the solver ──
    use_solver = preset.get("use_solver", True) and config.USE_SOLVER and is_solver_available()

    # ── Compute spot frequency data (for all paths) ──
    spot_freq_info: Optional[SpotFrequencyInfo] = None
    spot_freq_text = ""
    try:
        spot_freq_info = get_spot_frequency(scenario)
        spot_freq_text = format_spot_frequency_for_advisor(spot_freq_info)
    except Exception as e:
        if config.DEBUG:
            _status(f"  Spot frequency lookup error (non-fatal): {e}")

    # ── Step 1.5: Preflop lookup (pre-solved GTO ranges) ──
    # If this is a preflop scenario, try the instant lookup before falling back
    # to either the solver (which can't do preflop) or LLM-only mode.
    if scenario.current_street == "preflop":
        _status("Preflop detected — checking pre-solved GTO ranges...")
        t_pf = time.time()
        try:
            preflop_strategy = lookup_preflop_strategy(scenario)
        except Exception as e:
            preflop_strategy = None
            if config.DEBUG:
                _status(f"  Preflop lookup error (non-fatal): {e}")

        if preflop_strategy is not None:
            _status(
                f"  \u2713 Preflop GTO match in {time.time()-t_pf:.2f}s — "
                f"Best: {preflop_strategy.best_action} "
                f"({preflop_strategy.best_action_freq:.0%})"
            )
            # Generate advice using the preflop strategy (solver-quality data)
            _status("Generating advice from pre-solved GTO strategy...")
            t_adv = time.time()
            advice = generate_advice(
                query, scenario, preflop_strategy,
                opponent_notes=opponent_notes,
                spot_frequency_text=spot_freq_text,
                output_level=output_level,
            )
            _status(f"  \u2713 Generated in {time.time()-t_adv:.1f}s")
            source = "preflop_lookup"
            return {
                "advice": advice,
                "mode": mode,
                "scenario": scenario,
                "strategy": preflop_strategy,
                "sanity_note": "",
                "cached": True,  # Effectively cached — instant lookup
                "solve_time": 0.0,
                "source": source,
                "confidence": _CONFIDENCE_MAP.get(source, "low"),
                "parse_time": parse_time,
                "spot_frequency": spot_freq_info,
                "output_level": output_level,
            }
        else:
            _status("  No exact preflop match — falling back to LLM mode")
            # TexasSolver is postflop-only; always use LLM for preflop
            t_fb = time.time()
            advice = generate_fallback_advice(
                query, scenario, opponent_notes=opponent_notes, output_level=output_level,
            )
            source = "llm_fallback"
            _status(f"  \u2713 Generated in {time.time()-t_fb:.1f}s")
            return {
                "advice": advice,
                "mode": mode,
                "scenario": scenario,
                "strategy": None,
                "sanity_note": "",
                "cached": False,
                "solve_time": 0.0,
                "source": source,
                "confidence": _CONFIDENCE_MAP.get(source, "low"),
                "parse_time": parse_time,
                "spot_frequency": spot_freq_info,
                "output_level": output_level,
            }

    if not use_solver:
        # ── Fast / LLM-only mode ──
        _status("Generating GTO-approximate advice via Gemini (LLM-only)...")
        t1 = time.time()
        advice = generate_fallback_advice(query, scenario, opponent_notes=opponent_notes, output_level=output_level)
        source = "llm_only"
        _status(f"  ✓ Generated in {time.time()-t1:.1f}s")
        return {
            "advice": advice,
            "mode": mode,
            "scenario": scenario,
            "strategy": None,
            "sanity_note": "",
            "cached": False,
            "solve_time": 0.0,
            "source": source,
            "confidence": _CONFIDENCE_MAP.get(source, "low"),
            "parse_time": parse_time,
            "spot_frequency": spot_freq_info,
            "output_level": output_level,
        }

    # ── Step 2: Generate solver input file (with mode-specific settings) ──
    _status("Step 2/5: Generating solver input...")
    try:
        input_file = generate_solver_input(
            scenario,
            accuracy=preset.get("accuracy"),
            max_iterations=preset.get("max_iterations"),
            dump_rounds=preset.get("dump_rounds"),
        )
    except ValueError as e:
        _status(f"  ✗ Solver input error: {e}")
        _status("  Falling back to LLM-only mode...")
        advice = generate_fallback_advice(query, scenario, opponent_notes=opponent_notes, output_level=output_level)
        source = "llm_fallback"
        return {
            "advice": advice,
            "mode": mode,
            "scenario": scenario,
            "strategy": None,
            "sanity_note": "",
            "cached": False,
            "solve_time": 0.0,
            "source": source,
            "confidence": _CONFIDENCE_MAP.get(source, "low"),
            "parse_time": parse_time,
            "spot_frequency": spot_freq_info,
            "output_level": output_level,
        }

    # ── Step 2.5: Check cache ──
    cache_key = compute_cache_key(input_file)
    cached_file = cache_lookup(cache_key)
    cached = False
    solve_time = 0.0

    if cached_file:
        _status("📦 Cache hit! Loading saved solver result (instant)...")
        output_file = cached_file
        cached = True
    else:
        # ── Step 3: Run the solver ──
        exploitability = preset.get('accuracy', 0)
        accuracy_pct = 100 - exploitability if exploitability else '?'
        mode_label = f"{mode} mode — {accuracy_pct}% accuracy"
        _status(f"Step 3/5: Running TexasSolver ({mode_label})...")
        t2 = time.time()
        try:
            output_file = run_solver(input_file, timeout=preset.get("timeout"))
        except RuntimeError as e:
            _status(f"  ✗ Solver failed: {e}")
            _status("  Falling back to LLM-only mode...")
            advice = generate_fallback_advice(query, scenario, opponent_notes=opponent_notes, output_level=output_level)
            source = "llm_fallback"
            return {
                "advice": advice,
                "mode": mode,
                "scenario": scenario,
                "strategy": None,
                "sanity_note": "",
                "cached": False,
                "solve_time": 0.0,
                "source": source,
                "confidence": _CONFIDENCE_MAP.get(source, "low"),
                "parse_time": parse_time,
                "spot_frequency": spot_freq_info,
                "output_level": output_level,
            }

        if output_file is None:
            _status("  Solver unavailable — falling back to LLM-only...")
            advice = generate_fallback_advice(query, scenario, opponent_notes=opponent_notes, output_level=output_level)
            source = "llm_fallback"
            return {
                "advice": advice,
                "mode": mode,
                "scenario": scenario,
                "strategy": None,
                "sanity_note": "",
                "cached": False,
                "solve_time": 0.0,
                "source": source,
                "confidence": _CONFIDENCE_MAP.get(source, "low"),
                "parse_time": parse_time,
                "spot_frequency": spot_freq_info,
                "output_level": output_level,
            }

        solve_time = time.time() - t2
        _status(f"  ✓ Solved in {solve_time:.1f}s")

        # ── Cache the result ──
        cache_store(cache_key, output_file)
        _status("  ✓ Result cached for future lookups")

    # ── Step 4: Extract strategy ──
    _status("Step 4/5: Extracting strategy for your hand...")
    t3 = time.time()
    try:
        strategy = extract_strategy(output_file, scenario)
        _status(
            f"  ✓ Extracted in {time.time()-t3:.1f}s — "
            f"Best: {strategy.best_action} ({strategy.best_action_freq:.0%})"
        )
    except (ValueError, KeyError) as e:
        _status(f"  ✗ Strategy extraction failed: {e}")
        _status("  Falling back to LLM-only mode...")
        advice = generate_fallback_advice(query, scenario, opponent_notes=opponent_notes, output_level=output_level)
        source = "llm_fallback"
        return {
            "advice": advice,
            "mode": mode,
            "scenario": scenario,
            "strategy": None,
            "sanity_note": "",
            "cached": cached,
            "solve_time": solve_time,
            "source": source,
            "confidence": _CONFIDENCE_MAP.get(source, "low"),
            "parse_time": parse_time,
            "spot_frequency": spot_freq_info,
            "output_level": output_level,
        }

    # ── Step 4.5: Sanity check extreme frequencies ──
    sanity_note = ""
    _status("Running sanity check on solver output...")
    try:
        sanity_note = check_strategy_sanity(scenario, strategy)
        if sanity_note:
            _status("  ⚠ Extreme frequency detected — LLM review added")
        else:
            _status("  ✓ Strategy frequencies look normal")
    except Exception as e:
        if config.DEBUG:
            _status(f"  Sanity check error (non-fatal): {e}")

    # ── Step 5: Generate natural language advice ──
    _status("Step 5/5: Generating advice...")
    t4 = time.time()
    advice = generate_advice(
        query, scenario, strategy,
        sanity_note=sanity_note,
        opponent_notes=opponent_notes,
        spot_frequency_text=spot_freq_text,
        output_level=output_level,
    )
    _status(f"  ✓ Generated in {time.time()-t4:.1f}s")

    source = "solver_cached" if cached else "solver"
    return {
        "advice": advice,
        "mode": mode,
        "scenario": scenario,
        "strategy": strategy,
        "sanity_note": sanity_note,
        "cached": cached,
        "solve_time": solve_time,
        "source": source,
        "confidence": _CONFIDENCE_MAP.get(source, "low"),
        "parse_time": parse_time,
        "spot_frequency": spot_freq_info,
        "output_level": output_level,
    }


# ──────────────────────────────────────────────
# CLI Interface (wraps analyze_hand with printing)
# ──────────────────────────────────────────────

def run_pipeline(
    user_input: str,
    mode: str = "default",
    opponent_notes: str = "",
    output_level: str = "advanced",
) -> dict:
    """
    Run the full PokerGPT pipeline with CLI-friendly output.
    
    Args:
        user_input: Natural language poker question.
        mode: "fast", "default", or "pro".
        opponent_notes: Optional villain tendency description.
        output_level: "beginner" or "advanced".
        
    Returns:
        Full result dict from analyze_hand().
    """
    try:
        from rich.console import Console
        console = Console()
        def _status(msg: str):
            console.print(msg)
    except ImportError:
        def _status(msg: str):
            print(msg)

    result = analyze_hand(
        user_input,
        mode=mode,
        on_status=_status,
        opponent_notes=opponent_notes,
        output_level=output_level,
    )
    return result


def _display_result(result: dict, opponent_notes: str = "", pool_notes: str = "") -> None:
    """
    Display analysis results with rich formatting (tables, colors).
    Falls back to plain text if rich is unavailable.
    """
    strategy = result.get("strategy")
    advice = result.get("advice", "No advice generated.")
    confidence = result.get("confidence", "low")
    confidence_label = _CONFIDENCE_LABELS.get(confidence, confidence)
    source = result.get("source", "unknown")
    parse_time = result.get("parse_time", 0.0)
    solve_time = result.get("solve_time", 0.0)
    cached = result.get("cached", False)

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
    except ImportError:
        # Plain text fallback
        print(f"\n{'─' * 50}")
        print("NeuralGTO Advice:\n")

        if strategy and strategy.actions:
            print("GTO Strategy:")
            for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
                marker = "*" if action == strategy.best_action else " "
                print(f"  {marker} {action:>12s}  {freq*100:5.1f}%")
            print()

        print(advice)
        print(f"\n[Confidence: {confidence_label}]")
        badge = get_source_badge(source)
        if badge:
            print(badge)
        if opponent_notes:
            print(f'[Villain profile: "{opponent_notes}"]')
        if pool_notes:
            print(f'[Pool tendencies: "{pool_notes}"]')

        # Spot frequency
        spot_freq = result.get("spot_frequency")
        if spot_freq:
            print(f"\n📊 Spot Frequency: ~{spot_freq.frequency_pct}% of all hands")
            print(f"   {spot_freq.priority_label}")
            if spot_freq.similar_spots:
                print("   Also study:")
                for s in spot_freq.similar_spots[:3]:
                    print(f"     • {s}")

        print(f"{'─' * 50}")
        return

    console = Console()
    console.print()
    console.rule("[bold cyan]NeuralGTO Advice[/bold cyan]")

    # Strategy table
    if strategy and strategy.actions:
        table = Table(
            title="GTO Strategy",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Action", style="cyan", min_width=12)
        table.add_column("Freq", justify="right", style="green", min_width=8)
        table.add_column("Bar", min_width=20)

        for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
            pct = f"{freq * 100:.1f}%"
            bar_len = int(freq * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            style = "bold green" if action == strategy.best_action else ""
            table.add_row(action, pct, bar, style=style)

        console.print(table)
        console.print()

        # Range grid: show where the hand sits in the 13x13 grid
        if strategy.hand:
            render_range_grid_rich(strategy.actions, hand=strategy.hand)
            console.print()

    # Advice
    console.print(Panel(advice, title="Advice", border_style="green"))

    # Footer stats
    stats_parts: list[str] = []
    stats_parts.append(f"Confidence: [bold]{confidence_label}[/bold]")
    stats_parts.append(f"Source: {source}")
    if parse_time > 0:
        stats_parts.append(f"Parse: {parse_time:.1f}s")
    if solve_time > 0:
        stats_parts.append(f"Solve: {solve_time:.1f}s")
    if cached:
        stats_parts.append("Cache: [green]HIT[/green]")
    console.print(" · ".join(stats_parts))

    if opponent_notes:
        console.print(f'\n[dim]Villain profile: "{opponent_notes}"[/dim]')
    if pool_notes:
        console.print(f'\n[dim]Pool tendencies: "{pool_notes}"[/dim]')

    # Trust badge
    badge = get_source_badge(source)
    if badge:
        console.print(f"\n[bold]{badge}[/bold]")

    # Spot frequency
    spot_freq = result.get("spot_frequency")
    if spot_freq:
        console.print()
        freq_parts = [
            f"[bold]📊 Spot Frequency:[/bold] ~{spot_freq.frequency_pct}% of all hands",
            f"   {spot_freq.priority_label}",
        ]
        console.print("\n".join(freq_parts))
        if spot_freq.similar_spots:
            console.print("   [dim]Also study:[/dim]")
            for s in spot_freq.similar_spots[:3]:
                console.print(f"   [dim]• {s}[/dim]")

    console.rule()


# ──────────────────────────────────────────────
# Conversational Gap-Filling
# ──────────────────────────────────────────────

# Default assumptions when user doesn't specify
_DEFAULTS = {
    "effective_stack": "100bb",
    "game_type": "6-max cash",
    "pot_size": "estimated from action",
}

# Patterns to detect what's already specified
import re as _re

_HAS_STACK = _re.compile(
    r"\b(\d+)\s*bb\b|\beffective|\bstack|\bdeep\b|\bshort\b", _re.IGNORECASE
)
_HAS_POSITION = _re.compile(
    r"\b(?:button|btn|cutoff|cut-off|co|under\s*the\s*gun|utg|hijack|hj|"
    r"lojack|lj|small\s*blind|sb|big\s*blind|bb|mp|ep|lp|straddle)\b",
    _re.IGNORECASE,
)
_HAS_HAND = _re.compile(
    r"(?:pocket\s+\w+)|(?:pair\s+of\s+\w+)|"
    r"(?:[2-9TJQKA][hdcs]\s*[2-9TJQKA][hdcs])|"
    r"(?:[2-9TJQKA]{2}[so]?)|"
    r"(?:aces|kings|queens|jacks|tens|nines|eights|sevens|sixes)|"
    r"(?:ace[- ]king|king[- ]queen)|(?:big\s+slick)|"
    r"(?:rockets|cowboys|ladies|hooks|ducks)",
    _re.IGNORECASE,
)
_HAS_ACTION = _re.compile(
    r"\b(?:raise[sd]?|3bet|3-bet|4bet|open[sd]?|limp[sd]?|call[sd]?|check[sd]?|"
    r"bet[sd]?|fold[sd]?|jam[sd]?|shove[sd]?|all-?in)\b",
    _re.IGNORECASE,
)
_HAS_BOARD = _re.compile(
    r"\b(?:flop|turn|river|board)\b|"
    r"(?:[2-9TJQKA][hdcs]\s+[2-9TJQKA][hdcs]\s+[2-9TJQKA][hdcs])",
    _re.IGNORECASE,
)


def _fill_gaps_interactive(query: str) -> Optional[str]:
    """
    Check a query for missing details and prompt the user interactively.

    If the query is missing key information (hand, position, stack depth,
    action context), ask the user to provide it. The user can press Enter
    to accept the default. Returns the enriched query, or None if cancelled.

    Args:
        query: The user's original natural-language poker question.

    Returns:
        An enriched query string, or None if the user cancels.
    """
    gaps: list[tuple[str, str, str]] = []  # (field, prompt_text, default)

    if not _HAS_HAND.search(query):
        gaps.append((
            "hand",
            "What are your hole cards? (e.g. AKs, QQ, Jd Td)",
            "",
        ))

    if not _HAS_POSITION.search(query):
        gaps.append((
            "position",
            "What position are you in? (UTG / HJ / CO / BTN / SB / BB)",
            "",
        ))

    if not _HAS_ACTION.search(query):
        gaps.append((
            "action",
            "What's the action so far? (e.g. 'UTG raises to 3bb, I call')",
            "",
        ))

    if not _HAS_STACK.search(query):
        gaps.append((
            "stack",
            f"Effective stack depth? [default: {_DEFAULTS['effective_stack']}]",
            _DEFAULTS["effective_stack"],
        ))

    if not gaps:
        return query  # Query looks complete

    # Print summary of what's missing
    print("\n  I'd like a few more details for a better analysis:")
    additions: list[str] = []

    for field, prompt_text, default in gaps:
        try:
            answer = input(f"  → {prompt_text}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not answer and default:
            answer = default
            print(f"    (using default: {default})")
        elif not answer and not default:
            # Required field with no default — can't proceed without hand/position
            if field in ("hand", "position"):
                print(f"    This is required. Please try again with your full hand.")
                return None
            continue  # Skip optional field

        # Append the clarification to the query naturally
        if field == "hand":
            additions.append(f"I have {answer}")
        elif field == "position":
            additions.append(f"on the {answer}")
        elif field == "action":
            additions.append(answer)
        elif field == "stack":
            additions.append(f"{answer} effective")

    # Build enriched query
    if additions:
        enriched = query.rstrip(". ") + ". " + ". ".join(additions) + "."
        print(f"\n  → Enriched query: \"{enriched}\"\n")
        return enriched

    return query


def interactive_mode(
    default_mode: str = "default",
    default_opponent_notes: str = "",
    default_output_level: str = "advanced",
):
    """Run PokerGPT in interactive mode (REPL)."""
    print("=" * 60)
    print("  PokerGPT — Neuro-Symbolic Poker Advisor")
    print("  Powered by TexasSolver + Google Gemini")
    print("=" * 60)
    
    # Validate config
    warnings = config.validate_config()
    for w in warnings:
        print(f"  ⚠ {w}")
    
    if not config.GEMINI_API_KEY:
        print("\n  ERROR: GEMINI_API_KEY is required. Set it in .env file:")
        print("    echo GEMINI_API_KEY=your-key-here > .env")
        sys.exit(1)
    
    solver_status = "✓ Available" if is_solver_available() else "✗ Not found (using LLM-only fallback)"
    print(f"\n  Solver: {solver_status}")
    print(f"  Model: {config.GEMINI_MODEL}")
    print(f"  Mode: {default_mode}")
    print(f"  Output level: {default_output_level}")
    if default_opponent_notes:
        print(f"  Villain profile: {default_opponent_notes}")
    print(f"\nDescribe your poker hand and I'll give you GTO advice.")
    print("Type 'quit' or 'exit' to stop.")
    print("Type 'mode fast/default/pro' to change mode.")
    print("Type 'level beginner/advanced' to change output level.")
    print("Type 'opponent <description>' to set villain tendencies (e.g. 'opponent calling station').")
    print("Type 'opponent clear' to remove villain tendencies.")
    print("Type 'pool <description>' to set live game pool tendencies for session prep.")
    print("Type 'pool clear' to remove pool tendencies.")
    print("Type 'history' to see your recent queries.")
    print("Type 'import <filepath>' to import a hand history file.\n")
    
    current_mode = default_mode
    current_opponent_notes = default_opponent_notes
    current_pool_notes = ""
    current_output_level = default_output_level
    
    while True:
        try:
            user_input = input("🃏 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        
        # Mode switching
        if user_input.lower().startswith("mode "):
            new_mode = user_input.split(" ", 1)[1].strip().lower()
            if new_mode in config.MODE_PRESETS:
                current_mode = new_mode
                print(f"  → Switched to {current_mode} mode: {config.MODE_PRESETS[current_mode]['description']}")
            else:
                print(f"  Unknown mode '{new_mode}'. Use: fast, default, pro")
            continue

        # Output level switching
        if user_input.lower().startswith("level "):
            new_level = user_input.split(" ", 1)[1].strip().lower()
            if new_level in OUTPUT_LEVELS:
                current_output_level = new_level
                desc = (
                    "Plain-language coaching — no jargon"
                    if new_level == "beginner"
                    else "Full GTO analysis with frequencies and range logic"
                )
                print(f"  → Output level: {current_output_level} — {desc}")
            else:
                print(f"  Unknown level '{new_level}'. Use: beginner, advanced")
            continue

        # Villain tendency setting
        if user_input.lower().startswith("opponent "):
            notes = user_input.split(" ", 1)[1].strip()
            if notes.lower() == "clear":
                current_opponent_notes = ""
                print("  → Villain profile cleared. Advice will be pure GTO.")
            else:
                current_opponent_notes = notes
                print(f"  → Villain profile set: \"{current_opponent_notes}\"")
                print("  Advice will now include exploitative adjustments for this villain.")
            continue
        # Pool tendency setting (live game prep mode)
        if user_input.lower().startswith("pool "):
            notes = user_input.split(" ", 1)[1].strip()
            if notes.lower() == "clear":
                current_pool_notes = ""
                print("  \u2192 Pool profile cleared. Advice will be pure GTO.")
            else:
                current_pool_notes = notes
                print(f"  \u2192 Pool tendencies set: \"{current_pool_notes}\"")
                print("  All future advice will include pool-exploitative adjustments.")
                print("  (Use 'pool clear' to reset to pure GTO.)")
            continue        
        # History command
        if user_input.lower() in ("history", "hist"):
            entries = get_history(limit=10)
            if not entries:
                print("  No history yet.")
            else:
                print(f"  Last {len(entries)} queries:")
                for i, e in enumerate(entries, 1):
                    ts = e.get("timestamp", "")[:19].replace("T", " ")
                    hand = e.get("hero_hand", "?")
                    pos = e.get("hero_position", "?")
                    act = e.get("best_action", "?")
                    src = e.get("source", "?")
                    print(f"  {i:>2}. [{ts}] {hand} @ {pos} -> {act}  ({src})")
            continue

        # Import hand history command
        if user_input.lower().startswith("import "):
            hh_path = user_input.split(" ", 1)[1].strip().strip('"').strip("'")
            _handle_import_hh(
                hh_path,
                hero_name="",
                mode=current_mode,
                opponent_notes=current_opponent_notes,
            )
            continue

        try:
            # ── Conversational gap-filling ──
            # Before running the pipeline, check for missing info and prompt
            user_input = _fill_gaps_interactive(user_input)
            if user_input is None:
                # User cancelled during gap-filling
                continue

            result = run_pipeline(
                user_input,
                mode=current_mode,
                opponent_notes=_combine_opponent_pool_notes(
                    current_opponent_notes, current_pool_notes
                ),
                output_level=current_output_level,
            )
            _display_result(
                result,
                opponent_notes=current_opponent_notes,
                pool_notes=current_pool_notes,
            )
            log_query(result, user_input, opponent_notes=current_opponent_notes)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            if config.DEBUG:
                import traceback
                traceback.print_exc()
            print("Please try rephrasing your question.\n")


def _handle_import_hh(
    filepath: str,
    hero_name: str,
    mode: str = "default",
    opponent_notes: str = "",
    output_level: str = "advanced",
) -> None:
    """
    Import a hand history file, let user pick a hand, and analyze it.

    Args:
        filepath: Path to the hand history file.
        hero_name: Hero's player name (empty = auto-detect).
        mode: Analysis mode.
        opponent_notes: Villain tendency description.
        output_level: "beginner" or "advanced".
    """
    import os
    if not os.path.isfile(filepath):
        print(f"  \u2717 File not found: {filepath}")
        return

    # SECURITY: Prevent path traversal — only allow files in CWD or known dirs
    resolved = os.path.realpath(filepath)
    cwd = os.path.realpath(os.getcwd())
    home = os.path.realpath(str(Path.home()))
    if not (resolved.startswith(cwd) or resolved.startswith(home)):
        print(f"  \u2717 Access denied: file must be under your working directory or home folder.")
        return

    try:
        hands = parse_hand_history_file(filepath, hero_name=hero_name)
    except Exception as e:
        print(f"  \u2717 Error reading file: {e}")
        return

    if not hands:
        print("  No parseable hands found in file.")
        return

    print(f"\n  Found {len(hands)} hand(s):\n")
    summaries = hands_summary(hands)
    for s in summaries:
        print(f"    {s}")

    print()
    while True:
        try:
            choice = input(f"  Pick a hand (1-{len(hands)}) or 'cancel': ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice.lower() in ("cancel", "c", "q"):
            return
        if choice.isdigit() and 1 <= int(choice) <= len(hands):
            idx = int(choice) - 1
            break
        print(f"  Invalid choice. Enter a number 1-{len(hands)}.")

    selected = hands[idx]
    query = hand_to_query(selected)
    print(f"\n  Query: {query}\n")

    try:
        result = run_pipeline(query, mode=mode, opponent_notes=opponent_notes, output_level=output_level)
        _display_result(result, opponent_notes=opponent_notes)
        log_query(result, query, opponent_notes=opponent_notes)
    except Exception as e:
        print(f"\n\u274c Error: {e}")
        if config.DEBUG:
            import traceback
            traceback.print_exc()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PokerGPT — Neuro-Symbolic Poker Advisor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m poker_gpt.main
  python -m poker_gpt.main --query "I have AKs on the CO, BTN 3bets..."
  python -m poker_gpt.main --mode pro --query "..."
  python -m poker_gpt.main --mode fast --query "Quick preflop question..."
  python -m poker_gpt.main --no-solver --debug
  python -m poker_gpt.main --opponent "calling station, never folds" --query "I have QQ on BTN..."
  python -m poker_gpt.main --opponent "aggressive, raises every street" --query "..."
  python -m poker_gpt.main --pool "live 1/2, pool underbluffs, rarely value bets thin" --query "..."
  python -m poker_gpt.main --level beginner --query "I have QQ on the BTN..."
        """,
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Single query mode: provide the poker scenario directly",
    )
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["fast", "default", "pro"],
        default="default",
        help="Analysis mode: fast (LLM-only), default (solver), pro (high accuracy)",
    )
    parser.add_argument(
        "--no-solver",
        action="store_true",
        help="Force LLM-only mode (equivalent to --mode fast)",
    )
    parser.add_argument(
        "--opponent", "-o",
        type=str,
        default=None,
        help=(
            'Describe villain tendencies in plain English. Used to adjust the '
            'GTO recommendation exploitatively. '
            'Example: --opponent "calling station, never folds to bets"'
        ),
    )
    parser.add_argument(
        "--pool",
        type=str,
        default=None,
        help=(
            'Describe overall player-pool tendencies for session prep. '
            'Example: --pool "live 1/2, pool underbluffs, fit-or-fold postflop"'
        ),
    )
    parser.add_argument(
        "--level", "-l",
        type=str,
        choices=["beginner", "advanced"],
        default="advanced",
        help=(
            "Output level: beginner (plain-language coaching, no jargon) "
            "or advanced (full GTO analysis with frequencies)"
        ),
    )
    parser.add_argument(
        "--import-hh",
        type=str,
        default=None,
        metavar="FILE",
        help="Import a hand history file and analyze a hand from it",
    )
    parser.add_argument(
        "--hero-name",
        type=str,
        default="",
        help="Hero player name for hand history import (auto-detected if omitted)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show recent query history and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    
    args = parser.parse_args()
    
    if args.debug:
        config.DEBUG = True

    # --history flag: print recent history and exit
    if args.history:
        entries = get_history(limit=50)
        if not entries:
            print("No history yet.")
        else:
            print(f"Last {len(entries)} queries:\n")
            for i, e in enumerate(entries, 1):
                ts = e.get("timestamp", "")[:19].replace("T", " ")
                hand = e.get("hero_hand", "?")
                pos = e.get("hero_position", "?")
                act = e.get("best_action", "?")
                freq = e.get("best_action_freq")
                src = e.get("source", "?")
                mode_str = e.get("mode", "?")
                freq_str = f" ({freq:.0%})" if freq is not None else ""
                print(f"  {i:>2}. [{ts}] {hand} @ {pos} -> {act}{freq_str}  [{src}, {mode_str}]")
        sys.exit(0)

    # Startup environment check
    env_ok = config.check_env()
    if not env_ok:
        print("ERROR: GEMINI_API_KEY is required. Cannot continue.")
        sys.exit(1)
    
    mode = args.mode
    if args.no_solver:
        mode = "fast"
    
    opponent_notes = args.opponent or ""
    pool_notes = args.pool or ""
    output_level = args.level
    combined_notes = _combine_opponent_pool_notes(opponent_notes, pool_notes)

    if args.import_hh:
        # Hand history import mode
        _handle_import_hh(
            args.import_hh,
            hero_name=args.hero_name,
            mode=mode,
            opponent_notes=combined_notes,
            output_level=output_level,
        )
    elif args.query:
        # Single query mode
        result = run_pipeline(args.query, mode=mode, opponent_notes=combined_notes, output_level=output_level)
        _display_result(result, opponent_notes=opponent_notes, pool_notes=pool_notes)
        log_query(result, args.query, opponent_notes=combined_notes)
    else:
        # Interactive mode
        interactive_mode(default_mode=mode, default_opponent_notes=opponent_notes, default_output_level=output_level)


if __name__ == "__main__":
    main()
