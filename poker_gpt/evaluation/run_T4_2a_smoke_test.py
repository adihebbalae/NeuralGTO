"""
run_T4_2a_smoke_test.py — T4.2a Warm-Stop Semantic Pruning smoke test.

Runs hardcoded postflop spots through four conditions:
  1. Full solve (baseline)        — all bet sizes, convergence accuracy
  2. Warm-stop only (40 iter)     — partial solve for frequency extraction
  3. LLM-pruned solve             — Gemini selects which sizes to keep
  4. Threshold-pruned solve       — mechanical: drop actions with freq < 5%

Outputs a comparison table: solve time, nodes kept, strategy L1 distance.
Saves results to _dev/TASK_RESULTS/T4.2a/.

Created: 2026-02-28
Updated: 2026-03-03 — Bugfixes: RuntimeError→None, action name normalization,
  pruner no-op guard, strengthened pruner prompt.
Task: T4.2a

Usage:
    cd <project_root>
    python poker_gpt/evaluation/run_T4_2a_smoke_test.py --spots 1 --iterations 2
    python poker_gpt/evaluation/run_T4_2a_smoke_test.py  # all 5 spots, default settings
"""

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Force UTF-8 stdout/stderr to avoid encoding errors when output is redirected.
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from poker_gpt import config
from poker_gpt.poker_types import ScenarioData
from poker_gpt.solver_harness import (
    run_full_solve,
    run_warm_stop,
    run_pruned_solve,
    extract_action_frequencies,
    extract_and_normalize_frequencies,
    compute_strategy_l1_distance,
    measure_solve_time,
    normalize_action_names,
    is_pruning_noop,
)
from poker_gpt.llm_pruner import (
    suggest_pruning,
    threshold_prune,
    keep_actions_to_bet_sizes,
)
from poker_gpt.solver_runner import is_solver_available


# ──────────────────────────────────────────────
# Pre-expanded ranges (narrowed for smoke test performance)
# ──────────────────────────────────────────────

_BB_DEFEND_NARROW = (
    "AA,KK,QQ,JJ,TT,99,88,77,"
    "AKs,AQs,AJs,ATs,KQs,KJs,QJs,JTs,T9s,98s,87s,76s,"
    "AKo,AQo,AJo,KQo"
)

_BTN_OPEN_NARROW = (
    "AA,KK,QQ,JJ,TT,99,88,77,66,55,"
    "AKs,AQs,AJs,ATs,A9s,KQs,KJs,KTs,QJs,QTs,JTs,T9s,98s,"
    "AKo,AQo,AJo,ATo,KQo,KJo"
)

_CO_OPEN_NARROW = (
    "AA,KK,QQ,JJ,TT,99,88,77,66,"
    "AKs,AQs,AJs,ATs,A9s,KQs,KJs,QJs,JTs,T9s,98s,"
    "AKo,AQo,AJo,ATo,KQo"
)


SMOKE_TEST_SPOTS = [
    {
        "name": "Q-high two-tone (BTN vs BB)",
        "scenario": ScenarioData(
            hero_hand="AhKd",
            hero_position="BTN",
            board="Qs,Jh,2h",
            pot_size_bb=50.0,
            effective_stack_bb=200.0,
            current_street="flop",
            oop_range=_BB_DEFEND_NARROW,
            ip_range=_BTN_OPEN_NARROW,
            hero_is_ip=True,
            bet_sizes_pct=[33, 75],
            raise_sizes_pct=[60],
        ),
        "position_ip": "BTN",
        "position_oop": "BB",
    },
    {
        "name": "J-high two-tone (BTN vs BB)",
        "scenario": ScenarioData(
            hero_hand="TsTd",
            hero_position="BTN",
            board="Js,7c,2s",
            pot_size_bb=50.0,
            effective_stack_bb=200.0,
            current_street="flop",
            oop_range=_BB_DEFEND_NARROW,
            ip_range=_BTN_OPEN_NARROW,
            hero_is_ip=True,
            bet_sizes_pct=[33, 75],
            raise_sizes_pct=[60],
        ),
        "position_ip": "BTN",
        "position_oop": "BB",
    },
    {
        "name": "Paired board (BTN vs BB)",
        "scenario": ScenarioData(
            hero_hand="AcQh",
            hero_position="BTN",
            board="9s,9d,3h",
            pot_size_bb=50.0,
            effective_stack_bb=200.0,
            current_street="flop",
            oop_range=_BB_DEFEND_NARROW,
            ip_range=_BTN_OPEN_NARROW,
            hero_is_ip=True,
            bet_sizes_pct=[33, 75],
            raise_sizes_pct=[60],
        ),
        "position_ip": "BTN",
        "position_oop": "BB",
    },
    {
        "name": "T-high semi-connected (BTN vs BB)",
        "scenario": ScenarioData(
            hero_hand="KsQs",
            hero_position="BTN",
            board="Th,8d,4c",
            pot_size_bb=50.0,
            effective_stack_bb=200.0,
            current_street="flop",
            oop_range=_BB_DEFEND_NARROW,
            ip_range=_BTN_OPEN_NARROW,
            hero_is_ip=True,
            bet_sizes_pct=[33, 75],
            raise_sizes_pct=[60],
        ),
        "position_ip": "BTN",
        "position_oop": "BB",
    },
    {
        "name": "A-high dry rainbow (CO vs BB) [CTRL]",
        "scenario": ScenarioData(
            hero_hand="AdJd",
            hero_position="CO",
            board="Ah,8c,3d",
            pot_size_bb=50.0,
            effective_stack_bb=200.0,
            current_street="flop",
            oop_range=_BB_DEFEND_NARROW,
            ip_range=_CO_OPEN_NARROW,
            hero_is_ip=True,
            bet_sizes_pct=[33, 75],
            raise_sizes_pct=[60],
        ),
        "position_ip": "CO",
        "position_oop": "BB",
    },
]


def run_experiment(
    num_spots: int = 5,
    full_max_iter: int = 200,
    max_retries: int = 3,
) -> list[dict]:
    """Run the T4.2a smoke test experiment.

    Args:
        num_spots: How many spots to run (1–5).
        full_max_iter: Max CFR iterations for full/pruned solves.
        max_retries: Retry count for solver crashes (TexasSolver segfault workaround).

    Returns:
        List of per-spot result dicts.
    """
    print("=" * 70)
    print("T4.2a — Warm-Stop Semantic Pruning Smoke Test")
    print("=" * 70)
    print()

    # Preflight checks
    if not is_solver_available():
        print("ERROR: TexasSolver binary not found. Cannot run experiment.")
        print(f"  Expected at: {config.SOLVER_BINARY_PATH}")
        return []

    has_api = bool(config.GEMINI_API_KEY)
    if not has_api:
        print("WARNING: GEMINI_API_KEY not set. LLM pruning will be skipped.")

    config.ensure_work_dir()
    config.DEBUG = True

    # Solver settings
    full_accuracy = 5.0
    full_timeout = 1800
    warm_iterations = 40
    warm_timeout = 600

    spots = SMOKE_TEST_SPOTS[:num_spots]
    results: list[dict] = []
    experiment_start = time.perf_counter()
    spot_times: list[float] = []

    print(f"\n  Settings: full_accuracy={full_accuracy}%, full_max_iter={full_max_iter}, "
          f"warm_iter={warm_iterations}, max_retries={max_retries}")
    print(f"  Timeouts: full={full_timeout}s, warm={warm_timeout}s")
    print(f"  Solver: {config.SOLVER_BINARY_PATH}")
    print(f"  Spots: {len(spots)}  |  Started at: {datetime.now().strftime('%H:%M:%S')}")

    for i, spot in enumerate(spots):
        name = spot["name"]
        scenario = spot["scenario"]
        pos_ip = spot["position_ip"]
        pos_oop = spot["position_oop"]

        print(f"\n{'─' * 60}")
        elapsed_total = time.perf_counter() - experiment_start
        if spot_times:
            avg_spot_time = sum(spot_times) / len(spot_times)
            remaining = (len(spots) - i) * avg_spot_time
            eta = datetime.now() + timedelta(seconds=remaining)
            print(f"Spot {i+1}/{len(spots)}: {name}  "
                  f"[{datetime.now().strftime('%H:%M:%S')}]  "
                  f"ETA finish: {eta.strftime('%H:%M:%S')}")
        else:
            print(f"Spot {i+1}/{len(spots)}: {name}  "
                  f"[{datetime.now().strftime('%H:%M:%S')}]")
        print(f"  Board: {scenario.board}")
        print(f"  Stack: {scenario.effective_stack_bb:.0f} BB  |  "
              f"Pot: {scenario.pot_size_bb:.0f} BB  |  "
              f"SPR: {scenario.effective_stack_bb / scenario.pot_size_bb:.1f}")
        print(f"  Bet sizes: {scenario.bet_sizes_pct}  |  "
              f"Raise sizes: {scenario.raise_sizes_pct}")
        print(f"{'─' * 60}")

        spot_result: dict = {
            "name": name,
            "board": scenario.board,
            "effective_stack_bb": scenario.effective_stack_bb,
            "pot_size_bb": scenario.pot_size_bb,
            "bet_sizes": scenario.bet_sizes_pct,
        }

        # ── Step 1: Full solve (baseline) ──
        print("\n  [1/4] Running full solve (baseline)...")
        full_path, full_time = measure_solve_time(
            scenario,
            solve_fn="full",
            accuracy=full_accuracy,
            max_iterations=full_max_iter,
            timeout=full_timeout,
            input_tag=f"full_{i}",
        )

        if full_path is None:
            print("  ✗ Full solve FAILED. Skipping this spot.")
            spot_result["status"] = "full_solve_failed"
            results.append(spot_result)
            spot_times.append(time.perf_counter() - experiment_start - sum(spot_times))
            continue

        # BUG #2 FIX: Always normalize action names after extraction.
        # extract_and_normalize_frequencies() prevents passing raw chip-amount
        # names ("BET 16.500000") to pruners that expect "BET 33".
        full_freqs = extract_and_normalize_frequencies(
            full_path,
            pot_size_bb=scenario.pot_size_bb,
            effective_stack_bb=scenario.effective_stack_bb,
            bet_sizes_pct=scenario.bet_sizes_pct,
        )
        print(f"  ✓ Full solve: {full_time:.1f}s")
        if full_freqs:
            for action, freq in sorted(full_freqs.items(), key=lambda x: -x[1]):
                print(f"    {action}: {freq:.1%}")
        spot_result["full_solve_time_s"] = full_time
        spot_result["full_action_frequencies"] = full_freqs

        # ── Step 2: Warm-stop ──
        print(f"\n  [2/4] Running warm-stop ({warm_iterations} iterations)...")
        warm_path, warm_time = measure_solve_time(
            scenario,
            solve_fn="warm_stop",
            max_iterations=warm_iterations,
            timeout=warm_timeout,
            input_tag=f"warm_{i}",
        )

        if warm_path is None:
            print("  ✗ Warm-stop FAILED. Skipping LLM/threshold pruning.")
            spot_result["status"] = "warm_stop_failed"
            spot_times.append(time.perf_counter() - experiment_start - sum(spot_times))
            results.append(spot_result)
            continue

        # BUG #2 FIX: Normalize before passing to pruners.
        warm_freqs = extract_and_normalize_frequencies(
            warm_path,
            pot_size_bb=scenario.pot_size_bb,
            effective_stack_bb=scenario.effective_stack_bb,
            bet_sizes_pct=scenario.bet_sizes_pct,
        )
        print(f"  ✓ Warm-stop: {warm_time:.1f}s")
        if warm_freqs:
            for action, freq in sorted(warm_freqs.items(), key=lambda x: -x[1]):
                print(f"    {action}: {freq:.1%}")
        spot_result["warm_stop_time_s"] = warm_time
        spot_result["warm_action_frequencies"] = warm_freqs

        if warm_freqs is None:
            print("  ✗ Could not extract warm-stop frequencies.")
            spot_times.append(time.perf_counter() - experiment_start - sum(spot_times))
            spot_result["status"] = "warm_freq_extraction_failed"
            results.append(spot_result)
            continue

        # ── Step 3: LLM-pruned solve ──
        if has_api:
            print("\n  [3/4] Running LLM-pruned solve...")
            llm_decision = suggest_pruning(
                action_frequencies=warm_freqs,
                board=scenario.board,
                position_ip=pos_ip,
                position_oop=pos_oop,
                effective_stack_bb=scenario.effective_stack_bb,
                pot_size_bb=scenario.pot_size_bb,
                warm_iterations=warm_iterations,
            )

            if llm_decision is not None:
                print(f"    LLM keep: {llm_decision.keep_sizes}")
                print(f"    LLM prune: {llm_decision.prune_sizes}")
                print(f"    LLM reasoning: {llm_decision.reasoning[:120]}...")

                llm_bet_sizes = keep_actions_to_bet_sizes(llm_decision.keep_sizes)
                if not llm_bet_sizes:
                    llm_bet_sizes = list(scenario.bet_sizes_pct)
                    print("    ⚠ No bet sizes extracted from LLM decision; using all.")

                # BUG #3 FIX: Skip pruned solve if LLM kept everything.
                if is_pruning_noop(scenario.bet_sizes_pct, llm_bet_sizes):
                    print("    ⚠ LLM kept all bet sizes — pruned solve is "
                          "identical to full solve. Skipping.")
                    spot_result["llm_solve_time_s"] = full_time
                    spot_result["llm_l1_distance"] = 0.0
                    spot_result["llm_keep_sizes"] = llm_decision.keep_sizes
                    spot_result["llm_prune_sizes"] = llm_decision.prune_sizes
                    spot_result["llm_reasoning"] = llm_decision.reasoning
                    spot_result["llm_bet_sizes_pct"] = llm_bet_sizes
                    spot_result["llm_action_frequencies"] = full_freqs
                    spot_result["llm_noop"] = True
                else:
                    llm_path, llm_time = measure_solve_time(
                        scenario,
                        solve_fn="pruned",
                        keep_bet_sizes=llm_bet_sizes,
                        accuracy=full_accuracy,
                        max_iterations=full_max_iter,
                        timeout=full_timeout,
                        input_tag=f"llm_{i}",
                    )

                    if llm_path is not None:
                        llm_l1 = compute_strategy_l1_distance(full_path, llm_path)
                        llm_freqs = extract_and_normalize_frequencies(
                            llm_path,
                            pot_size_bb=scenario.pot_size_bb,
                            effective_stack_bb=scenario.effective_stack_bb,
                            bet_sizes_pct=scenario.bet_sizes_pct,
                        )
                        print(f"  ✓ LLM-pruned solve: {llm_time:.1f}s, L1={llm_l1}")
                        spot_result["llm_solve_time_s"] = llm_time
                        spot_result["llm_l1_distance"] = llm_l1
                        spot_result["llm_keep_sizes"] = llm_decision.keep_sizes
                        spot_result["llm_prune_sizes"] = llm_decision.prune_sizes
                        spot_result["llm_reasoning"] = llm_decision.reasoning
                        spot_result["llm_bet_sizes_pct"] = llm_bet_sizes
                        spot_result["llm_action_frequencies"] = llm_freqs
                    else:
                        print("  ✗ LLM-pruned solve FAILED.")
                        spot_result["llm_solve_time_s"] = None
                        spot_result["llm_l1_distance"] = None
            else:
                print("  ✗ LLM pruning suggestion FAILED (no decision returned).")
                spot_result["llm_solve_time_s"] = None
                spot_result["llm_l1_distance"] = None
        else:
            spot_result["llm_solve_time_s"] = None
            spot_result["llm_l1_distance"] = None
            print("\n  [3/4] LLM pruning SKIPPED (no API key).")

        # ── Step 4: Threshold-pruned solve ──
        print("\n  [4/4] Running threshold-pruned solve (freq < 5%)...")
        thresh_decision = threshold_prune(warm_freqs, threshold=0.05)
        print(f"    Threshold keep: {thresh_decision.keep_sizes}")
        print(f"    Threshold prune: {thresh_decision.prune_sizes}")

        thresh_bet_sizes = keep_actions_to_bet_sizes(thresh_decision.keep_sizes)
        if not thresh_bet_sizes:
            thresh_bet_sizes = list(scenario.bet_sizes_pct)
            print("    ⚠ No bet sizes after threshold; using all.")

        # BUG #3 FIX: Skip pruned solve if threshold kept everything.
        if is_pruning_noop(scenario.bet_sizes_pct, thresh_bet_sizes):
            print("    ⚠ Threshold kept all bet sizes — skipping pruned solve.")
            spot_result["thresh_solve_time_s"] = full_time
            spot_result["thresh_l1_distance"] = 0.0
            spot_result["thresh_keep_sizes"] = thresh_decision.keep_sizes
            spot_result["thresh_prune_sizes"] = thresh_decision.prune_sizes
            spot_result["thresh_bet_sizes_pct"] = thresh_bet_sizes
            spot_result["thresh_action_frequencies"] = full_freqs
            spot_result["thresh_noop"] = True
        else:
            thresh_path, thresh_time = measure_solve_time(
                scenario,
                solve_fn="pruned",
                keep_bet_sizes=thresh_bet_sizes,
                accuracy=full_accuracy,
                max_iterations=full_max_iter,
                timeout=full_timeout,
                input_tag=f"thresh_{i}",
            )

            if thresh_path is not None:
                thresh_l1 = compute_strategy_l1_distance(full_path, thresh_path)
                thresh_freqs = extract_and_normalize_frequencies(
                    thresh_path,
                    pot_size_bb=scenario.pot_size_bb,
                    effective_stack_bb=scenario.effective_stack_bb,
                    bet_sizes_pct=scenario.bet_sizes_pct,
                )
                print(f"  ✓ Threshold-pruned solve: {thresh_time:.1f}s, L1={thresh_l1}")
                spot_result["thresh_solve_time_s"] = thresh_time
                spot_result["thresh_l1_distance"] = thresh_l1
                spot_result["thresh_keep_sizes"] = thresh_decision.keep_sizes
                spot_result["thresh_prune_sizes"] = thresh_decision.prune_sizes
                spot_result["thresh_bet_sizes_pct"] = thresh_bet_sizes
                spot_result["thresh_action_frequencies"] = thresh_freqs
            else:
                print("  ✗ Threshold-pruned solve FAILED.")
                spot_result["thresh_solve_time_s"] = None
                spot_result["thresh_l1_distance"] = None

        spot_result["status"] = "completed"
        results.append(spot_result)

        spot_elapsed = time.perf_counter() - experiment_start - sum(spot_times)
        spot_times.append(spot_elapsed)
        print(f"\n  ── Spot {i+1} done in {spot_elapsed:.0f}s "
              f"({time.perf_counter() - experiment_start:.0f}s total) ──")

        if has_api and i < len(spots) - 1:
            time.sleep(4)

    total_elapsed = time.perf_counter() - experiment_start
    print(f"\n  Total time: {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)")
    print(f"  Finished: {datetime.now().strftime('%H:%M:%S')}")
    _print_summary(results)
    _save_results(results, total_elapsed)
    return results


def _print_summary(results: list[dict]) -> None:
    """Print a formatted comparison table."""
    print("\n")
    print("=" * 90)
    print("RESULTS SUMMARY — T4.2a Warm-Stop Semantic Pruning")
    print("=" * 90)
    print()
    header = (f"{'Spot':<35} {'Full(s)':<10} {'LLM(s)':<10} "
              f"{'Thr(s)':<10} {'LLM L1':<10} {'Thr L1':<10}")
    print(header)
    print("─" * 85)

    for r in results:
        name = r.get("name", "?")[:34]
        full_t = r.get("full_solve_time_s")
        llm_t = r.get("llm_solve_time_s")
        thresh_t = r.get("thresh_solve_time_s")
        llm_l1 = r.get("llm_l1_distance")
        thresh_l1 = r.get("thresh_l1_distance")

        full_s = f"{full_t:.1f}" if full_t is not None else "FAIL"
        llm_s = f"{llm_t:.1f}" if llm_t is not None else "FAIL"
        noop = " *" if r.get("llm_noop") else ""
        llm_s += noop
        thresh_s = f"{thresh_t:.1f}" if thresh_t is not None else "FAIL"
        noop_t = " *" if r.get("thresh_noop") else ""
        thresh_s += noop_t
        llm_l1_s = f"{llm_l1:.4f}" if llm_l1 is not None else "N/A"
        thresh_l1_s = f"{thresh_l1:.4f}" if thresh_l1 is not None else "N/A"

        print(f"{name:<35} {full_s:<10} {llm_s:<10} "
              f"{thresh_s:<10} {llm_l1_s:<10} {thresh_l1_s:<10}")

    print()
    print("  * = pruning was a no-op (all bet sizes kept); "
          "time/L1 copied from full solve")
    print()


def _save_results(results: list[dict], total_elapsed: float = 0.0) -> None:
    """Save results JSON to _dev/TASK_RESULTS/T4.2a/."""
    output_dir = _PROJECT_ROOT / "_dev" / "TASK_RESULTS" / "T4.2a"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "smoke_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to: {output_file}")

    summary_file = output_dir / "summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("T4.2a — Warm-Stop Semantic Pruning Smoke Test Results\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total time: {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)\n")
        f.write(f"Spots tested: {len(results)}\n")
        f.write(f"Model: {config.GEMINI_MODEL}\n\n")

        for r in results:
            f.write(f"--- {r.get('name', '?')} ---\n")
            f.write(f"  Board: {r.get('board', '?')}\n")
            f.write(f"  Status: {r.get('status', '?')}\n")
            f.write(f"  Full solve: {r.get('full_solve_time_s', '?')}s\n")
            f.write(f"  LLM solve:  {r.get('llm_solve_time_s', '?')}s  "
                    f"L1={r.get('llm_l1_distance', '?')}\n")
            f.write(f"  Thr solve:  {r.get('thresh_solve_time_s', '?')}s  "
                    f"L1={r.get('thresh_l1_distance', '?')}\n")
            if r.get("llm_noop"):
                f.write("  (LLM pruning was a no-op)\n")
            if r.get("thresh_noop"):
                f.write("  (Threshold pruning was a no-op)\n")
            f.write("\n")

    print(f"Summary saved to: {summary_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="T4.2a Warm-Stop Semantic Pruning smoke test"
    )
    parser.add_argument(
        "--spots", type=int, default=5,
        help="Number of spots to run (1-5, default: 5)",
    )
    parser.add_argument(
        "--iterations", type=int, default=200,
        help="Max CFR iterations for full/pruned solves (default: 200)",
    )
    parser.add_argument(
        "--max_retries", type=int, default=3,
        help="Retry count for solver crashes (default: 3)",
    )
    args = parser.parse_args()

    spots = max(1, min(5, args.spots))
    run_experiment(
        num_spots=spots,
        full_max_iter=args.iterations,
        max_retries=args.max_retries,
    )


if __name__ == "__main__":
    main()
