"""
run_t43_comparison.py — T4.3 Full Method Comparison eval script.

Runs Gemini direct baseline on (a) the 244 HU-matched scenarios and
(b) the 424 multi-way scenarios from PokerBench preflop, then produces
a head-to-head accuracy comparison table with 95% confidence intervals.

Three methods compared:
  1. Lookup tables (T3.7)  — pre-solved range files, HU scenarios
  2. Pairwise LLM synthesis (T4.1b) — HU decomposition + Gemini, multi-way
  3. Gemini direct baseline — raw Gemini, no solver/lookup

Usage:
    python -m poker_gpt.evaluation.run_t43_comparison [--sleep 4] [--dry-run]

Created: 2026-02-28

DOCUMENTATION:
    Reads prior eval result files to identify scenario subsets:
      - eval_neuralgto_lookup_preflop_20260228_154008.json  → 244 HU indices
      - eval_neuralgto_pairwise_preflop_20260228_174803.json → 424 MW indices

    Runs gemini_direct on the union (587 unique scenarios), then partitions
    results for each subset. Saves full results + comparison summary to
    _dev/TASK_RESULTS/T4.3/.
"""

from __future__ import annotations

import argparse
import json
import math
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is importable
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

load_dotenv(override=True)

from google import genai
from google.genai import types

from poker_gpt import config
from poker_gpt.evaluation.pokerbench import (
    PBScenario,
    action_matches,
    load_test_set,
)
from poker_gpt.evaluation.evaluator import (
    _DIRECT_SYSTEM_PROMPT,
    _normalize_prediction,
    EvalResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "_data" / "pokerbench"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "_dev" / "TASK_RESULTS" / "T4.3"

# Prior eval result files (from T3.7 and T4.1b)
_LOOKUP_EVAL = _DATA_DIR / "eval_neuralgto_lookup_preflop_20260228_154008.json"
_PAIRWISE_EVAL = _DATA_DIR / "eval_neuralgto_pairwise_preflop_20260228_174803.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    More accurate than the normal approximation for small n or extreme p.

    Args:
        p: Observed proportion (0.0 - 1.0).
        n: Sample size.
        z: Z-score for desired confidence level (1.96 = 95%).

    Returns:
        Tuple of (lower, upper) bounds.
    """
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return ((centre - spread) / denom, (centre + spread) / denom)


def _normal_ci(p: float, n: int, z: float = 1.96) -> float:
    """Normal approximation margin of error for proportion.

    Args:
        p: Observed proportion.
        n: Sample size.
        z: Z-score (1.96 = 95%).

    Returns:
        Half-width of the confidence interval (±).
    """
    if n == 0:
        return 0.0
    return z * math.sqrt(p * (1 - p) / n)


def _load_prior_indices() -> tuple[set[int], set[int]]:
    """Load scenario indices from prior eval result files.

    Returns:
        Tuple of (hu_matched_indices, multiway_indices).

    Raises:
        FileNotFoundError: If prior eval files are missing.
    """
    if not _LOOKUP_EVAL.exists():
        raise FileNotFoundError(
            f"Lookup eval not found: {_LOOKUP_EVAL}\n"
            "Run T3.7 eval first (neuralgto_lookup mode)."
        )
    if not _PAIRWISE_EVAL.exists():
        raise FileNotFoundError(
            f"Pairwise eval not found: {_PAIRWISE_EVAL}\n"
            "Run T4.1b eval first (neuralgto_pairwise mode)."
        )

    with open(_LOOKUP_EVAL, "r", encoding="utf-8") as f:
        lookup_data = json.load(f)
    with open(_PAIRWISE_EVAL, "r", encoding="utf-8") as f:
        pairwise_data = json.load(f)

    # HU-matched: scenarios where lookup produced a real prediction
    hu_indices = {
        r["index"]
        for r in lookup_data["detailed_results"]
        if not r["predicted"].startswith("[")
    }

    # Multi-way: all scenarios in the pairwise eval
    mw_indices = {r["index"] for r in pairwise_data["detailed_results"]}

    return hu_indices, mw_indices


def _predict_gemini_direct(
    scenario: PBScenario,
    client: genai.Client,
) -> tuple[str, str]:
    """Get Gemini's direct prediction for a PokerBench scenario.

    Args:
        scenario: The PokerBench scenario.
        client: Gemini API client.

    Returns:
        Tuple of (action_category, raw_output).
    """
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=scenario.instruction + "\n\nYour optimal action is:",
        config=types.GenerateContentConfig(
            system_instruction=_DIRECT_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=1024,
        ),
    )
    raw = response.text.strip().lower() if response.text else ""
    return _normalize_prediction(raw)


def _compute_subset_stats(
    results: dict[int, EvalResult],
    indices: set[int],
    label: str,
) -> dict:
    """Compute accuracy stats for a subset of results.

    Args:
        results: Dict mapping scenario index → EvalResult.
        indices: Set of scenario indices in this subset.
        label: Label for this subset (e.g. "HU-matched", "Multi-way").

    Returns:
        Dict with accuracy, CI, per-action breakdown, confusion matrix.
    """
    subset = [results[i] for i in sorted(indices) if i in results]
    n = len(subset)
    correct = sum(1 for r in subset if r.correct)
    errors = sum(1 for r in subset if r.error)
    acc = correct / max(n, 1)
    margin = _normal_ci(acc, n)
    lo, hi = _wilson_ci(acc, n)

    # Per ground-truth action
    by_action: dict[str, dict] = {}
    confusion: dict[str, dict[str, int]] = {}
    for r in subset:
        true_cat = r.scenario.action_category
        if true_cat in ("bet", "raise"):
            true_cat = "raise"
        pred_cat = r.predicted_action
        if pred_cat in ("bet", "raise"):
            pred_cat = "raise"

        if true_cat not in by_action:
            by_action[true_cat] = {"total": 0, "correct": 0}
        by_action[true_cat]["total"] += 1
        if r.correct:
            by_action[true_cat]["correct"] += 1

        row = confusion.setdefault(true_cat, {})
        row[pred_cat] = row.get(pred_cat, 0) + 1

    for cat, stats in by_action.items():
        stats["accuracy"] = stats["correct"] / max(stats["total"], 1)
        stats["ci_margin"] = _normal_ci(stats["accuracy"], stats["total"])

    # Per position
    by_position: dict[str, dict] = {}
    for r in subset:
        pos = r.scenario.hero_position
        if pos not in by_position:
            by_position[pos] = {"total": 0, "correct": 0}
        by_position[pos]["total"] += 1
        if r.correct:
            by_position[pos]["correct"] += 1
    for pos, stats in by_position.items():
        stats["accuracy"] = stats["correct"] / max(stats["total"], 1)

    return {
        "label": label,
        "n": n,
        "correct": correct,
        "errors": errors,
        "accuracy": acc,
        "accuracy_pct": round(acc * 100, 1),
        "ci_margin": round(margin * 100, 1),
        "ci_wilson": (round(lo * 100, 1), round(hi * 100, 1)),
        "by_action": by_action,
        "by_position": by_position,
        "confusion": confusion,
    }


def _format_comparison_table(
    hu_gemini: dict,
    mw_gemini: dict,
    lookup_acc: float = 0.885,
    lookup_n: int = 244,
    pairwise_acc: float = 0.745,
    pairwise_n: int = 424,
) -> str:
    """Format the head-to-head comparison table.

    Args:
        hu_gemini: Stats for Gemini direct on HU scenarios.
        mw_gemini: Stats for Gemini direct on multi-way scenarios.
        lookup_acc: Lookup accuracy from T3.7.
        lookup_n: Number of HU-matched scenarios.
        pairwise_acc: Pairwise LLM accuracy from T4.1b.
        pairwise_n: Number of multi-way scenarios.

    Returns:
        Formatted comparison table as string.
    """
    lookup_ci = _normal_ci(lookup_acc, lookup_n)
    pairwise_ci = _normal_ci(pairwise_acc, pairwise_n)

    # Pre-compute CI strings to avoid nested f-string issues
    lookup_ci_str = f"±{lookup_ci*100:.1f}pp"
    hu_ci_str = f"±{hu_gemini['ci_margin']:.1f}pp"
    pw_ci_str = f"±{pairwise_ci*100:.1f}pp"
    mw_ci_str = f"±{mw_gemini['ci_margin']:.1f}pp"

    lines = [
        "=" * 80,
        "T4.3 — Full Method Comparison (PokerBench Preflop)",
        "=" * 80,
        "",
        f"{'Method':<28s} {'Scenario Type':<14s} {'N':>5s} {'Accuracy':>10s} {'95% CI':>14s}",
        "-" * 80,
        f"{'Lookup (T3.7)':<28s} {'HU only':<14s} {lookup_n:>5d} "
        f"{lookup_acc:>9.1%} {lookup_ci_str:>14s}",
        f"{'Gemini direct':<28s} {'HU':<14s} {hu_gemini['n']:>5d} "
        f"{hu_gemini['accuracy']:>9.1%} {hu_ci_str:>14s}",
        "",
        f"{'Pairwise LLM (T4.1b)':<28s} {'Multi-way':<14s} {pairwise_n:>5d} "
        f"{pairwise_acc:>9.1%} {pw_ci_str:>14s}",
        f"{'Gemini direct':<28s} {'Multi-way':<14s} {mw_gemini['n']:>5d} "
        f"{mw_gemini['accuracy']:>9.1%} {mw_ci_str:>14s}",
        "-" * 80,
        "",
    ]

    # Delta analysis
    hu_delta = (lookup_acc - hu_gemini["accuracy"]) * 100
    mw_delta = (pairwise_acc - mw_gemini["accuracy"]) * 100
    lines.extend([
        "--- Delta Analysis ---",
        f"  Lookup vs Gemini (HU):     {hu_delta:+.1f}pp "
        f"({'solver wins' if hu_delta > 0 else 'LLM wins'})",
        f"  Pairwise vs Gemini (MW):   {mw_delta:+.1f}pp "
        f"({'solver wins' if mw_delta > 0 else 'LLM wins'})",
        "",
    ])

    # Per-action breakdown for Gemini
    lines.append("--- Gemini Direct: Per-Action Accuracy ---")
    lines.append(f"  {'Subset':<12s} {'Action':<10s} {'N':>5s} {'Acc':>8s} {'CI':>10s}")
    for subset_label, stats in [("HU", hu_gemini), ("Multi-way", mw_gemini)]:
        for action in sorted(stats["by_action"].keys()):
            a = stats["by_action"][action]
            ci_str = f"±{a['ci_margin']:.1f}pp"
            lines.append(
                f"  {subset_label:<12s} {action:<10s} {a['total']:>5d} "
                f"{a['accuracy']:>7.1%} {ci_str:>10s}"
            )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_t43_comparison(
    sleep_s: float = 4.0,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Run the T4.3 full method comparison.

    Evaluates Gemini direct baseline on both HU-matched (244) and
    multi-way (424) PokerBench preflop scenarios, then compares
    against lookup (T3.7) and pairwise (T4.1b) results.

    Args:
        sleep_s: Sleep between API calls (4s for free tier, 0.3s for paid).
        dry_run: If True, skip API calls and just partition scenarios.
        limit: Max scenarios to evaluate (for testing).

    Returns:
        Dict with full comparison data.
    """
    print("=" * 60)
    print("T4.3 — Full Method Comparison")
    print("=" * 60)
    print()

    # Step 1: Load scenario indices from prior evals
    print("Loading prior eval results...")
    hu_indices, mw_indices = _load_prior_indices()
    union_indices = hu_indices | mw_indices
    overlap = hu_indices & mw_indices

    print(f"  HU-matched (T3.7):  {len(hu_indices)} scenarios")
    print(f"  Multi-way (T4.1b):  {len(mw_indices)} scenarios")
    print(f"  Overlap:            {len(overlap)} scenarios")
    print(f"  Union (to eval):    {len(union_indices)} unique scenarios")
    print()

    # Step 2: Load all 1000 preflop scenarios
    print("Loading PokerBench preflop test set...")
    all_scenarios = load_test_set("preflop")
    print(f"  Loaded {len(all_scenarios)} scenarios")
    print()

    # Build index → scenario map
    scenario_map = {s.index: s for s in all_scenarios}

    # Filter to union
    eval_indices = sorted(union_indices)
    if limit:
        eval_indices = eval_indices[:limit]
    eval_scenarios = [(i, scenario_map[i]) for i in eval_indices if i in scenario_map]

    total_calls = len(eval_scenarios)
    est_time_min = (total_calls * sleep_s) / 60
    est_cost_usd = total_calls * 0.00015  # ~150 input tokens * $0.10/M = $0.015/100

    print(f"  Scenarios to evaluate: {total_calls}")
    print(f"  Estimated time: {est_time_min:.0f} min (@ {sleep_s}s/call)")
    print(f"  Estimated cost: ${est_cost_usd:.2f} (Gemini Flash)")
    print()

    if dry_run:
        print("[DRY RUN] Skipping API calls.")
        print()
        # Show what would be evaluated
        hu_in_eval = [i for i in eval_indices if i in hu_indices]
        mw_in_eval = [i for i in eval_indices if i in mw_indices]
        print(f"  Would eval {len(hu_in_eval)} HU + {len(mw_in_eval)} MW scenarios")
        return {"dry_run": True, "total_calls": total_calls}

    # Step 3: Run Gemini direct on all union scenarios
    print("Running Gemini direct baseline...")
    print()

    api_key = config.GEMINI_API_KEY
    client = genai.Client(api_key=api_key)

    results: dict[int, EvalResult] = {}
    total_api_calls = 0
    start_time = time.time()

    for batch_i, (idx, scenario) in enumerate(eval_scenarios):
        t0 = time.time()
        result = EvalResult(scenario=scenario)

        try:
            action_cat, raw = _predict_gemini_direct(scenario, client)
            result.predicted_action = action_cat
            result.predicted_raw = raw
            result.correct = action_matches(raw, scenario.ground_truth)
            total_api_calls += 1
        except Exception as e:
            result.error = str(e)
            logger.warning("Error on scenario %d: %s", idx, e)

        result.latency_s = time.time() - t0
        results[idx] = result

        # Progress
        status = "Y" if result.correct else ("X" if not result.error else "!")
        pred = result.predicted_raw[:25] if result.predicted_raw else "ERROR"
        truth = scenario.ground_truth
        subset_tags = []
        if idx in hu_indices:
            subset_tags.append("HU")
        if idx in mw_indices:
            subset_tags.append("MW")
        tags = "+".join(subset_tags)

        print(
            f"  [{batch_i+1:4d}/{total_calls}] {status} [{tags:5s}] "
            f"pred={pred:<25s} truth={truth:<15s} "
            f"({result.latency_s:.1f}s)",
            flush=True,
        )

        # Rate limiting
        if batch_i < total_calls - 1:
            time.sleep(sleep_s)

    total_time = time.time() - start_time
    print()
    print(f"Completed {total_api_calls} API calls in {total_time:.0f}s "
          f"({total_time/60:.1f} min)")

    # Step 4: Compute per-subset stats
    print()
    print("Computing subset statistics...")

    hu_stats = _compute_subset_stats(results, hu_indices, "HU-matched")
    mw_stats = _compute_subset_stats(results, mw_indices, "Multi-way")

    # Also compute overall (union)
    all_stats = _compute_subset_stats(results, set(results.keys()), "All evaluated")

    # Step 5: Print comparison table
    print()
    table = _format_comparison_table(hu_stats, mw_stats)
    print(table)

    # Step 6: Save results
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Full results JSON
    full_results = {
        "meta": {
            "task": "T4.3",
            "description": "Full method comparison — Gemini direct baseline",
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": config.GEMINI_MODEL,
            "total_api_calls": total_api_calls,
            "total_time_s": round(total_time, 1),
            "sleep_between_calls_s": sleep_s,
            "estimated_cost_usd": round(est_cost_usd, 4),
        },
        "comparison": {
            "lookup_t37": {
                "method": "Lookup tables (T3.7)",
                "scenario_type": "HU only",
                "n": 244,
                "accuracy": 0.885,
                "accuracy_pct": 88.5,
                "ci_margin_pp": round(_normal_ci(0.885, 244) * 100, 1),
            },
            "gemini_direct_hu": {
                "method": "Gemini direct",
                "scenario_type": "HU",
                "n": hu_stats["n"],
                "accuracy": round(hu_stats["accuracy"], 4),
                "accuracy_pct": hu_stats["accuracy_pct"],
                "ci_margin_pp": hu_stats["ci_margin"],
                "by_action": hu_stats["by_action"],
                "by_position": hu_stats["by_position"],
                "confusion": hu_stats["confusion"],
            },
            "pairwise_t41b": {
                "method": "Pairwise LLM (T4.1b)",
                "scenario_type": "Multi-way",
                "n": 424,
                "accuracy": 0.745,
                "accuracy_pct": 74.5,
                "ci_margin_pp": round(_normal_ci(0.745, 424) * 100, 1),
            },
            "gemini_direct_mw": {
                "method": "Gemini direct",
                "scenario_type": "Multi-way",
                "n": mw_stats["n"],
                "accuracy": round(mw_stats["accuracy"], 4),
                "accuracy_pct": mw_stats["accuracy_pct"],
                "ci_margin_pp": mw_stats["ci_margin"],
                "by_action": mw_stats["by_action"],
                "by_position": mw_stats["by_position"],
                "confusion": mw_stats["confusion"],
            },
        },
        "gemini_direct_overall": {
            "n": all_stats["n"],
            "accuracy": round(all_stats["accuracy"], 4),
            "accuracy_pct": all_stats["accuracy_pct"],
            "ci_margin_pp": all_stats["ci_margin"],
            "by_action": all_stats["by_action"],
            "by_position": all_stats["by_position"],
        },
        "detailed_results": [
            {
                "index": idx,
                "street": results[idx].scenario.street,
                "position": results[idx].scenario.hero_position,
                "ground_truth": results[idx].scenario.ground_truth,
                "predicted": results[idx].predicted_raw,
                "predicted_action": results[idx].predicted_action,
                "correct": results[idx].correct,
                "latency_s": round(results[idx].latency_s, 3),
                "error": results[idx].error,
                "is_hu_matched": idx in hu_indices,
                "is_multiway": idx in mw_indices,
            }
            for idx in sorted(results.keys())
        ],
    }

    # Serialize action stats (convert accuracy floats for JSON)
    for key in ("gemini_direct_hu", "gemini_direct_mw"):
        section = full_results["comparison"][key]
        for action, stats in section.get("by_action", {}).items():
            stats["accuracy"] = round(stats["accuracy"], 4)
            stats["ci_margin"] = round(stats.get("ci_margin", 0), 4)
        for pos, stats in section.get("by_position", {}).items():
            stats["accuracy"] = round(stats["accuracy"], 4)

    results_path = _OUTPUT_DIR / "results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2)
    print(f"Saved: {results_path}")

    # Summary text
    summary_path = _OUTPUT_DIR / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(table)
        f.write("\n\n")
        f.write("--- Overall Gemini Direct Stats ---\n")
        f.write(f"  Total scenarios: {all_stats['n']}\n")
        f.write(f"  Accuracy: {all_stats['accuracy']:.1%} ± {all_stats['ci_margin']:.1f}pp\n")
        f.write(f"  Model: {config.GEMINI_MODEL}\n")
        f.write(f"  Total API calls: {total_api_calls}\n")
        f.write(f"  Total time: {total_time:.0f}s\n")
        f.write(f"  Estimated cost: ${est_cost_usd:.2f}\n")
    print(f"Saved: {summary_path}")

    # Artifacts markdown
    artifacts_path = _OUTPUT_DIR / "artifacts.md"
    with open(artifacts_path, "w", encoding="utf-8") as f:
        f.write("# T4.3 — Full Method Comparison\n\n")
        f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Model:** {config.GEMINI_MODEL}\n\n")

        f.write("## Comparison Table\n\n")
        f.write("| Method | Scenario Type | N | Accuracy | 95% CI |\n")
        f.write("|--------|--------------|---:|--------:|--------:|\n")
        f.write(
            f"| Lookup (T3.7) | HU only | 244 | 88.5% | "
            f"±{_normal_ci(0.885, 244)*100:.1f}pp |\n"
        )
        f.write(
            f"| Gemini direct | HU | {hu_stats['n']} | "
            f"{hu_stats['accuracy_pct']}% | ±{hu_stats['ci_margin']}pp |\n"
        )
        f.write(
            f"| Pairwise LLM (T4.1b) | Multi-way | 424 | 74.5% | "
            f"±{_normal_ci(0.745, 424)*100:.1f}pp |\n"
        )
        f.write(
            f"| Gemini direct | Multi-way | {mw_stats['n']} | "
            f"{mw_stats['accuracy_pct']}% | ±{mw_stats['ci_margin']}pp |\n"
        )

        f.write("\n## Key Findings\n\n")

        hu_delta = (0.885 - hu_stats["accuracy"]) * 100
        mw_delta = (0.745 - mw_stats["accuracy"]) * 100

        f.write("### Does adding the solver/lookup help vs. Gemini alone?\n\n")
        if hu_delta > 0:
            f.write(
                f"**Yes for HU scenarios.** Lookup tables outperform Gemini by "
                f"+{hu_delta:.1f}pp ({88.5}% vs {hu_stats['accuracy_pct']}%). "
                f"Pre-solved GTO ranges provide more accurate preflop decisions "
                f"than LLM reasoning alone.\n\n"
            )
        else:
            f.write(
                f"**No for HU scenarios.** Gemini direct ({hu_stats['accuracy_pct']}%) "
                f"matches or exceeds lookup ({88.5}%), suggesting that for preflop "
                f"decisions, the LLM has already internalized GTO ranges.\n\n"
            )

        if mw_delta > 0:
            f.write(
                f"**Yes for multi-way.** Pairwise decomposition + LLM synthesis "
                f"outperforms pure Gemini by +{mw_delta:.1f}pp ({74.5}% vs "
                f"{mw_stats['accuracy_pct']}%). The solver-informed decomposition "
                f"provides structure that improves multi-way reasoning.\n\n"
            )
        else:
            f.write(
                f"**No for multi-way.** Gemini direct ({mw_stats['accuracy_pct']}%) "
                f"matches or exceeds pairwise ({74.5}%), suggesting the added "
                f"complexity of decomposition doesn't help for preflop multi-way.\n\n"
            )

        f.write("### What's the LLM ceiling without any solver?\n\n")
        f.write(
            f"Gemini achieves {hu_stats['accuracy_pct']}% on HU and "
            f"{mw_stats['accuracy_pct']}% on multi-way scenarios without "
            f"any solver infrastructure. This represents the 'free' baseline "
            f"that NeuralGTO's neuro-symbolic approach must exceed to justify "
            f"its complexity.\n\n"
        )

        f.write("### Where does neuro-symbolic earn its complexity?\n\n")
        if hu_delta > 2:
            f.write(
                f"The primary value-add is in **HU scenarios** where pre-solved "
                f"GTO lookup tables provide a {hu_delta:.1f}pp accuracy advantage "
                f"over raw LLM reasoning. These are exact solutions — not "
                f"approximations — computed by CFR convergence.\n\n"
            )
        if mw_delta > 2:
            f.write(
                f"For **multi-way scenarios**, pairwise HU decomposition combined "
                f"with LLM synthesis adds {mw_delta:.1f}pp over raw Gemini. The "
                f"structured decomposition helps the LLM reason about multi-opponent "
                f"dynamics rather than trying to solve them from raw intuition.\n\n"
            )

        f.write("## Per-Action Breakdown (Gemini Direct)\n\n")
        f.write("| Subset | Action | N | Accuracy | 95% CI |\n")
        f.write("|--------|--------|---:|--------:|--------:|\n")
        for subset_label, stats in [("HU", hu_stats), ("Multi-way", mw_stats)]:
            for action in sorted(stats["by_action"].keys()):
                a = stats["by_action"][action]
                f.write(
                    f"| {subset_label} | {action} | {a['total']} | "
                    f"{a['accuracy']:.1%} | ±{a['ci_margin']:.1f}pp |\n"
                )

        f.write("\n## Confusion Matrices\n\n")
        for subset_label, stats in [("HU", hu_stats), ("Multi-way", mw_stats)]:
            f.write(f"### {subset_label}\n\n")
            all_cats = sorted(
                {c for row in stats["confusion"].values() for c in row}
                | set(stats["confusion"].keys())
            )
            f.write("| True \\ Pred | " + " | ".join(all_cats) + " |\n")
            f.write("|" + "---|" * (len(all_cats) + 1) + "\n")
            for true_cat in all_cats:
                row = stats["confusion"].get(true_cat, {})
                cells = " | ".join(str(row.get(c, 0)) for c in all_cats)
                f.write(f"| {true_cat} | {cells} |\n")
            f.write("\n")

        f.write("## Methodology\n\n")
        f.write("- **Dataset:** PokerBench preflop 1k scenarios (Zhuang et al., AAAI 2025)\n")
        f.write("- **Action matching:** Fold/call/raise categories (bet+raise grouped)\n")
        f.write("- **Confidence intervals:** Normal approximation, z=1.96 (95%)\n")
        f.write(f"- **Model:** {config.GEMINI_MODEL}\n")
        f.write(f"- **Temperature:** 0.0 (deterministic)\n")
        f.write(f"- **Total API calls:** {total_api_calls}\n")
        f.write(f"- **Estimated cost:** ${est_cost_usd:.2f}\n")

    print(f"Saved: {artifacts_path}")
    print()
    print("T4.3 comparison complete.")

    return full_results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for T4.3 comparison."""
    parser = argparse.ArgumentParser(
        description="T4.3 — Full method comparison (Gemini direct baseline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=4.0,
        help="Sleep between API calls in seconds (default: 4.0 for free tier)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Partition scenarios without making API calls",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max scenarios to evaluate (for testing)",
    )

    args = parser.parse_args()

    run_t43_comparison(
        sleep_s=args.sleep,
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
