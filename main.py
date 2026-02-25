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
    - default: Solver low accuracy     — 2% exploitability, 100 iterations (~1-2 min)
    - pro:     Solver high accuracy    — 0.3% exploitability, 500 iterations (~4-6 min)

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
from poker_gpt.nl_advisor import generate_advice, generate_fallback_advice
from poker_gpt.sanity_checker import check_strategy_sanity
from poker_gpt.cache import compute_cache_key, cache_lookup, cache_store


def analyze_hand(
    query: str,
    mode: str = "default",
    on_status: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Core analysis function — used by both CLI and web UI.
    
    Runs the full PokerGPT pipeline with caching, sanity checking,
    and mode-specific solver settings.
    
    Args:
        query: Natural language poker question.
        mode: Analysis mode — "fast", "default", or "pro".
        on_status: Optional callback for progress updates (e.g., for web UI).
        
    Returns:
        dict with keys: advice, mode, scenario, strategy, sanity_note,
        cached, solve_time, source.
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

    # ── Check if we should use the solver ──
    use_solver = preset.get("use_solver", True) and config.USE_SOLVER and is_solver_available()

    if not use_solver:
        # ── Fast / LLM-only mode ──
        _status("Generating GTO-approximate advice via Gemini (LLM-only)...")
        t1 = time.time()
        advice = generate_fallback_advice(query, scenario)
        _status(f"  ✓ Generated in {time.time()-t1:.1f}s")
        return {
            "advice": advice,
            "mode": mode,
            "scenario": scenario,
            "strategy": None,
            "sanity_note": "",
            "cached": False,
            "solve_time": 0.0,
            "source": "llm_only",
        }

    # ── Step 2: Generate solver input file (with mode-specific settings) ──
    _status("Step 2/5: Generating solver input...")
    input_file = generate_solver_input(
        scenario,
        accuracy=preset.get("accuracy"),
        max_iterations=preset.get("max_iterations"),
        dump_rounds=preset.get("dump_rounds"),
    )

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
        mode_label = f"{mode} mode — accuracy {preset.get('accuracy', '?')}%"
        _status(f"Step 3/5: Running TexasSolver ({mode_label})...")
        t2 = time.time()
        try:
            output_file = run_solver(input_file, timeout=preset.get("timeout"))
        except RuntimeError as e:
            _status(f"  ✗ Solver failed: {e}")
            _status("  Falling back to LLM-only mode...")
            advice = generate_fallback_advice(query, scenario)
            return {
                "advice": advice,
                "mode": mode,
                "scenario": scenario,
                "strategy": None,
                "sanity_note": "",
                "cached": False,
                "solve_time": 0.0,
                "source": "llm_fallback",
            }

        if output_file is None:
            _status("  Solver unavailable — falling back to LLM-only...")
            advice = generate_fallback_advice(query, scenario)
            return {
                "advice": advice,
                "mode": mode,
                "scenario": scenario,
                "strategy": None,
                "sanity_note": "",
                "cached": False,
                "solve_time": 0.0,
                "source": "llm_fallback",
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
        advice = generate_fallback_advice(query, scenario)
        return {
            "advice": advice,
            "mode": mode,
            "scenario": scenario,
            "strategy": None,
            "sanity_note": "",
            "cached": cached,
            "solve_time": solve_time,
            "source": "llm_fallback",
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
    advice = generate_advice(query, scenario, strategy, sanity_note=sanity_note)
    _status(f"  ✓ Generated in {time.time()-t4:.1f}s")

    return {
        "advice": advice,
        "mode": mode,
        "scenario": scenario,
        "strategy": strategy,
        "sanity_note": sanity_note,
        "cached": cached,
        "solve_time": solve_time,
        "source": "solver_cached" if cached else "solver",
    }


# ──────────────────────────────────────────────
# CLI Interface (wraps analyze_hand with printing)
# ──────────────────────────────────────────────

def run_pipeline(user_input: str, mode: str = "default") -> str:
    """
    Run the full PokerGPT pipeline with CLI-friendly output.
    
    Args:
        user_input: Natural language poker question.
        mode: "fast", "default", or "pro".
        
    Returns:
        Natural language advice string.
    """
    result = analyze_hand(user_input, mode=mode, on_status=lambda msg: print(msg))
    return result["advice"]


def interactive_mode(default_mode: str = "default"):
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
    print(f"\nDescribe your poker hand and I'll give you GTO advice.")
    print("Type 'quit' or 'exit' to stop.")
    print("Type 'mode fast/default/pro' to change mode.\n")
    
    current_mode = default_mode
    
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
        
        try:
            advice = run_pipeline(user_input, mode=current_mode)
            print(f"\n{'─' * 50}")
            print(f"🎯 PokerGPT Advice:\n")
            print(advice)
            print(f"\n{'─' * 50}\n")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            if config.DEBUG:
                import traceback
                traceback.print_exc()
            print("Please try rephrasing your question.\n")


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
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    
    args = parser.parse_args()
    
    if args.debug:
        config.DEBUG = True
    
    mode = args.mode
    if args.no_solver:
        mode = "fast"
    
    if args.query:
        # Single query mode
        advice = run_pipeline(args.query, mode=mode)
        print(f"\n{'─' * 50}")
        print(f"🎯 PokerGPT Advice:\n")
        print(advice)
        print(f"\n{'─' * 50}")
    else:
        # Interactive mode
        interactive_mode(default_mode=mode)


if __name__ == "__main__":
    main()
