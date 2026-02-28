"""
run_eval.py — CLI entry point for PokerBench evaluation.

Usage:
    # Quick test (10 scenarios, gemini baseline)
    python -m poker_gpt.evaluation.run_eval --mode gemini_direct --split preflop --limit 10

    # Full preflop evaluation (1000 scenarios, ~8 min)
    python -m poker_gpt.evaluation.run_eval --mode gemini_direct --split preflop

    # Compare baseline vs enhanced prompting
    python -m poker_gpt.evaluation.run_eval --mode neuralgto_fast --split preflop --limit 100

    # Full evaluation (11k scenarios, ~1.5 hours)
    python -m poker_gpt.evaluation.run_eval --mode gemini_direct --split all

Created: 2026-02-27
"""

from __future__ import annotations

import argparse
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv(override=True)


def main() -> None:
    """Run PokerBench evaluation from command line."""
    parser = argparse.ArgumentParser(
        description="Evaluate NeuralGTO against PokerBench dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Quick test:     %(prog)s --limit 10
  Full preflop:   %(prog)s --split preflop
  Compare modes:  %(prog)s --mode neuralgto_fast --split preflop --limit 100
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["gemini_direct", "neuralgto_fast", "neuralgto_lookup"],
        default="neuralgto_lookup",
        help="Evaluation mode (default: neuralgto_lookup)",
    )
    parser.add_argument(
        "--split",
        choices=["preflop", "postflop", "all"],
        default="preflop",
        help="Dataset split to evaluate (default: preflop)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max scenarios to evaluate (default: all in split)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to disk",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Print dataset statistics and exit (no API calls)",
    )

    args = parser.parse_args()

    if args.stats_only:
        from poker_gpt.evaluation.pokerbench import load_test_set, dataset_stats
        print(f"Loading PokerBench {args.split} test set...")
        scenarios = load_test_set(args.split, limit=args.limit)
        stats = dataset_stats(scenarios)
        print(f"\nTotal scenarios: {stats['total']}")
        print(f"\nBy street:")
        for k, v in stats["by_street"].items():
            print(f"  {k}: {v}")
        print(f"\nBy position:")
        for k, v in stats["by_position"].items():
            print(f"  {k}: {v}")
        print(f"\nBy action:")
        for k, v in stats["by_action"].items():
            print(f"  {k}: {v}")
        return

    from poker_gpt.evaluation.evaluator import run_evaluation

    def progress(current: int, total: int, result) -> None:
        status = "Y" if result.correct else ("X" if not result.error else "!")
        pred = result.predicted_raw[:20] if result.predicted_raw else "ERROR"
        truth = result.scenario.ground_truth
        print(
            f"  [{current:4d}/{total}] {status} "
            f"predicted={pred:20s} truth={truth:15s} "
            f"({result.latency_s:.1f}s)",
            flush=True,
        )

    print(f"Running PokerBench evaluation:")
    print(f"  Mode:  {args.mode}")
    print(f"  Split: {args.split}")
    print(f"  Limit: {args.limit or 'all'}")
    print()

    report = run_evaluation(
        mode=args.mode,
        split=args.split,
        limit=args.limit,
        progress_callback=progress,
        save_results=not args.no_save,
    )

    print()
    print(report.summary())


if __name__ == "__main__":
    main()
