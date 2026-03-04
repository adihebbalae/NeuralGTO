"""
solver_harness.py — Solver wrapper for warm-stop and pruned-tree experiments.

Wraps solver_runner.py and solver_input.py to provide:
- Warm-stop solving (run N iterations, capture partial output)
- Pruned-tree solving (rebuild solver input with reduced bet sizes, full solve)
- Full-tree solving (standard solve with all bet sizes)

Used by the T4.2a Warm-Stop Semantic Pruning experiment pipeline.

Created: 2026-02-28

DOCUMENTATION:
- Builds on solver_runner.py (subprocess execution) and solver_input.py (input generation)
- Never duplicates subprocess logic — delegates to solver_runner.run_solver()
- Returns None on any failure (never raises)
- All paths via config.*
"""

import json
import time
from pathlib import Path
from typing import Optional

from poker_gpt import config
from poker_gpt.poker_types import ScenarioData
from poker_gpt.solver_input import generate_solver_input
from poker_gpt.solver_runner import run_solver, is_solver_available
from poker_gpt import solver_pruner_cpp


# TexasSolver v0.2.0 Linux binary has a non-deterministic segfault bug
# during CFR iteration 0 on certain board+range combinations.  The crash
# is board-specific (some boards crash 100% of attempts, others never)
# but also has a stochastic component (the same board may crash on one
# run and succeed on the next).  Adding retry logic helps the stochastic
# cases; deterministic crashes will fail after MAX_RETRIES attempts.
MAX_RETRIES = 3


def run_warm_stop(
    scenario: ScenarioData,
    max_iterations: int = 20,
    accuracy: float = 100.0,
    timeout: int = 60,
    input_tag: str = "warmstop",
) -> Optional[Path]:
    """
    Run the solver for a limited number of iterations (warm-stop).

    Generates a solver input file with the given iteration cap, runs the solver,
    and returns the path to the partial output JSON. The high accuracy value
    (100.0) ensures the solver always runs the full max_iterations rather than
    stopping early on convergence.

    Args:
        scenario: Parsed poker scenario with ranges, board, bet sizes, etc.
        max_iterations: Number of CFR iterations to run (default: 20).
        accuracy: Solver accuracy target (% pot). Set high to force max_iterations.
        timeout: Subprocess timeout in seconds.
        input_tag: File tag for the input/output files (avoids collisions).

    Returns:
        Path to the partial output JSON file, or None on failure.
    """
    if not is_solver_available():
        if config.DEBUG:
            print("[SOLVER_HARNESS] Solver not available for warm-stop.")
        return None

    try:
        config.ensure_work_dir()

        input_path = config.WORK_DIR / f"solver_input_{input_tag}.txt"
        output_path = config.WORK_DIR / f"output_{input_tag}.json"

        # Remove stale output from prior runs before solving
        _clean_stale_output(output_path)

        # Generate solver input with limited iterations
        generate_solver_input(
            scenario,
            output_path=input_path,
            accuracy=accuracy,
            max_iterations=max_iterations,
            dump_rounds=config.SOLVER_DUMP_ROUNDS,
        )

        # Patch the dump_result line to use our tagged output filename
        _patch_output_path(input_path, output_path)

        # Run solver with retry logic (TexasSolver v0.2.0 segfault workaround)
        for attempt in range(1, MAX_RETRIES + 1):
            _clean_stale_output(output_path)
            try:
                result_path = run_solver(input_file=input_path, timeout=timeout)
            except Exception as exc:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Warm-stop attempt {attempt}/{MAX_RETRIES} "
                          f"failed: {exc}")
                result_path = None

            # Recover output and validate JSON integrity
            candidate = _resolve_output_candidate(output_path, result_path)
            if candidate is not None and _validate_solver_json(candidate):
                return candidate
            elif candidate is not None:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Warm-stop output truncated/corrupt "
                          f"(attempt {attempt}/{MAX_RETRIES})")

            # No valid output — retry if attempts remain
            if attempt < MAX_RETRIES:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Retrying warm-stop ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(1)

        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Warm-stop output not found at {output_path} "
                  f"after {MAX_RETRIES} attempts")
        return None

    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Warm-stop failed: {e}")
        return None


def run_full_solve(
    scenario: ScenarioData,
    accuracy: float = None,
    max_iterations: int = None,
    timeout: int = None,
    input_tag: str = "full",
) -> Optional[Path]:
    """
    Run a standard full solver solve.

    Args:
        scenario: Parsed poker scenario.
        accuracy: Solver accuracy (% pot). None = use config default.
        max_iterations: Max iterations. None = use config default.
        timeout: Subprocess timeout. None = use config default.
        input_tag: File tag for input/output files.

    Returns:
        Path to the output JSON file, or None on failure.
    """
    if not is_solver_available():
        if config.DEBUG:
            print("[SOLVER_HARNESS] Solver not available for full solve.")
        return None

    try:
        config.ensure_work_dir()

        input_path = config.WORK_DIR / f"solver_input_{input_tag}.txt"
        output_path = config.WORK_DIR / f"output_{input_tag}.json"

        # Remove stale output from prior runs before solving
        _clean_stale_output(output_path)

        generate_solver_input(
            scenario,
            output_path=input_path,
            accuracy=accuracy,
            max_iterations=max_iterations,
            dump_rounds=config.SOLVER_DUMP_ROUNDS,
        )

        _patch_output_path(input_path, output_path)

        # Run solver with retry logic (TexasSolver v0.2.0 segfault workaround)
        for attempt in range(1, MAX_RETRIES + 1):
            _clean_stale_output(output_path)
            try:
                result_path = run_solver(input_file=input_path, timeout=timeout)
            except Exception as exc:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Full solve attempt {attempt}/{MAX_RETRIES} "
                          f"failed: {exc}")
                result_path = None

            # Recover output and validate JSON integrity
            candidate = _resolve_output_candidate(output_path, result_path)
            if candidate is not None and _validate_solver_json(candidate):
                return candidate
            elif candidate is not None:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Full solve output truncated/corrupt "
                          f"(attempt {attempt}/{MAX_RETRIES})")

            # No valid output — retry if attempts remain
            if attempt < MAX_RETRIES:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Retrying full solve ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(1)

        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Full solve output not found at {output_path} "
                  f"after {MAX_RETRIES} attempts")
        return None

    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Full solve failed: {e}")
        return None


def run_pruned_solve(
    scenario: ScenarioData,
    keep_bet_sizes: list[str],
    accuracy: float = None,
    max_iterations: int = None,
    timeout: int = None,
    input_tag: str = "pruned",
) -> Optional[Path]:
    """
    Run solver with a reduced set of bet sizes (pruned tree).

    Creates a modified ScenarioData with only the bet sizes specified in
    keep_bet_sizes, then runs a full solve on the smaller tree.

    Args:
        scenario: Original parsed poker scenario.
        keep_bet_sizes: List of bet size percentages to keep, e.g. [33, 67].
            These are integers matching the solver's bet size format.
        accuracy: Solver accuracy. None = use config default.
        max_iterations: Max iterations. None = use config default.
        timeout: Subprocess timeout. None = use config default.
        input_tag: File tag for input/output files.

    Returns:
        Path to the output JSON file, or None on failure.
    """
    if not is_solver_available():
        if config.DEBUG:
            print("[SOLVER_HARNESS] Solver not available for pruned solve.")
        return None

    try:
        config.ensure_work_dir()

        # Create modified scenario with pruned bet sizes
        pruned_scenario = _create_pruned_scenario(scenario, keep_bet_sizes)

        input_path = config.WORK_DIR / f"solver_input_{input_tag}.txt"
        output_path = config.WORK_DIR / f"output_{input_tag}.json"

        # Remove stale output from prior runs before solving
        _clean_stale_output(output_path)

        generate_solver_input(
            pruned_scenario,
            output_path=input_path,
            accuracy=accuracy,
            max_iterations=max_iterations,
            dump_rounds=config.SOLVER_DUMP_ROUNDS,
        )

        _patch_output_path(input_path, output_path)

        # Run solver with retry logic (TexasSolver v0.2.0 segfault workaround)
        for attempt in range(1, MAX_RETRIES + 1):
            _clean_stale_output(output_path)
            try:
                result_path = run_solver(input_file=input_path, timeout=timeout)
            except Exception as exc:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Pruned solve attempt {attempt}/{MAX_RETRIES} "
                          f"failed: {exc}")
                result_path = None

            # Recover output and validate JSON integrity
            candidate = _resolve_output_candidate(output_path, result_path)
            if candidate is not None and _validate_solver_json(candidate):
                return candidate
            elif candidate is not None:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Pruned solve output truncated/corrupt "
                          f"(attempt {attempt}/{MAX_RETRIES})")

            # No valid output — retry if attempts remain
            if attempt < MAX_RETRIES:
                if config.DEBUG:
                    print(f"[SOLVER_HARNESS] Retrying pruned solve ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(1)

        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Pruned solve output not found at {output_path} "
                  f"after {MAX_RETRIES} attempts")
        return None

    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Pruned solve failed: {e}")
        return None


def extract_action_frequencies(output_path: Path) -> Optional[dict]:
    """
    Parse a solver output JSON and extract per-action average frequencies.

    Reads the root action node's strategy and computes the average frequency
    of each action across all hand combos. Used to identify near-zero-frequency
    actions for pruning decisions.

    Args:
        output_path: Path to the solver output JSON.

    Returns:
        Dict mapping action names to average frequencies, e.g.
        {"CHECK": 0.35, "BET 33": 0.25, "BET 67": 0.30, "BET 100": 0.10},
        or None on failure.
    """
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            tree = json.load(f)

        root = _find_root_action_node(tree)
        if root is None:
            if config.DEBUG:
                print("[SOLVER_HARNESS] No action node found in output JSON.")
            return None

        actions = root.get("actions", [])
        strategy_data = root.get("strategy", {}).get("strategy", {})

        if not actions or not strategy_data:
            if config.DEBUG:
                print("[SOLVER_HARNESS] Empty actions or strategy in output.")
            return None

        n_actions = len(actions)
        totals = [0.0] * n_actions
        count = 0

        for hand, freqs in strategy_data.items():
            for i in range(min(n_actions, len(freqs))):
                totals[i] += freqs[i]
            count += 1

        if count == 0:
            return None

        result = {}
        for i, action_name in enumerate(actions):
            result[action_name] = round(totals[i] / count, 4)

        return result

    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Failed to extract frequencies: {e}")
        return None


def extract_and_normalize_frequencies(
    output_path: Path,
    pot_size_bb: float,
    effective_stack_bb: float,
    bet_sizes_pct: list[int] | None = None,
) -> Optional[dict]:
    """
    Extract action frequencies and normalize names in one step.

    Convenience wrapper that calls extract_action_frequencies() then
    normalize_action_names().  Prevents callers from accidentally passing
    raw chip-amount names (e.g. ``BET 16.500000``) to the LLM pruner,
    which expects pot-percentage names (e.g. ``BET 33``).

    Uses C++ implementation when available for ~5-10% speedup (T4.2c).

    Args:
        output_path: Path to the solver output JSON.
        pot_size_bb: Pot size in big blinds.
        effective_stack_bb: Effective stack in big blinds.
        bet_sizes_pct: Configured bet sizes (e.g. [33, 75]).

    Returns:
        Dict mapping normalised action names to avg frequencies, or None.
    """
    # Try C++ implementation first (T4.2c optimization)
    if solver_pruner_cpp.is_cpp_available():
        result = solver_pruner_cpp.extract_and_normalize_cpp(
            output_path,
            pot_size_bb,
            effective_stack_bb,
            bet_sizes_pct or []
        )
        if result is not None:
            return result
        # C++ failed, fall through to Python
    
    # Python fallback
    raw = extract_action_frequencies(output_path)
    if raw is None:
        return None
    return normalize_action_names(
        raw,
        pot_size_bb=pot_size_bb,
        effective_stack_bb=effective_stack_bb,
        bet_sizes_pct=bet_sizes_pct,
    )


def compute_strategy_l1_distance(
    baseline_path: Path,
    comparison_path: Path,
) -> Optional[float]:
    """
    Compute L1 distance between two solver strategies at the root node.

    For each hand combo present in both strategies, sums the absolute difference
    of frequencies for each shared action. Returns the average L1 distance
    across all shared combos.

    Args:
        baseline_path: Path to the baseline (full-tree) solver output JSON.
        comparison_path: Path to the comparison solver output JSON.

    Returns:
        Average L1 distance (0.0 = identical, higher = more divergent),
        or None on failure.
    """
    try:
        baseline_root = _load_root_node(baseline_path)
        comparison_root = _load_root_node(comparison_path)

        if baseline_root is None or comparison_root is None:
            return None

        b_actions = baseline_root.get("actions", [])
        c_actions = comparison_root.get("actions", [])
        b_strategy = baseline_root.get("strategy", {}).get("strategy", {})
        c_strategy = comparison_root.get("strategy", {}).get("strategy", {})

        if not b_strategy or not c_strategy:
            return None

        # Find shared actions — map comparison actions to baseline indices
        shared_actions = [a for a in c_actions if a in b_actions]
        if not shared_actions:
            # No overlapping actions — strategies are incomparable
            # Assign max distance
            return 1.0

        total_l1 = 0.0
        n_hands = 0

        for hand in b_strategy:
            if hand not in c_strategy:
                continue

            b_freqs = b_strategy[hand]
            c_freqs = c_strategy[hand]

            hand_l1 = 0.0
            for action in shared_actions:
                b_idx = b_actions.index(action)
                c_idx = c_actions.index(action)

                b_val = b_freqs[b_idx] if b_idx < len(b_freqs) else 0.0
                c_val = c_freqs[c_idx] if c_idx < len(c_freqs) else 0.0
                hand_l1 += abs(b_val - c_val)

            # Also account for baseline actions not in comparison (pruned away)
            for action in b_actions:
                if action not in shared_actions:
                    b_idx = b_actions.index(action)
                    b_val = b_freqs[b_idx] if b_idx < len(b_freqs) else 0.0
                    hand_l1 += b_val  # Pruned action's full freq is "error"

            total_l1 += hand_l1
            n_hands += 1

        if n_hands == 0:
            return None

        return round(total_l1 / n_hands, 4)

    except Exception as e:
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] L1 distance computation failed: {e}")
        return None


def measure_solve_time(
    scenario: ScenarioData,
    solve_fn: str = "full",
    **kwargs,
) -> tuple[Optional[Path], float]:
    """
    Run a solve and measure wall-clock time.

    Args:
        scenario: Parsed poker scenario.
        solve_fn: Which solve function to use: "full", "warm_stop", or "pruned".
        **kwargs: Additional arguments passed to the solve function.

    Returns:
        Tuple of (output_path, elapsed_seconds). output_path is None on failure.
    """
    start = time.perf_counter()

    if solve_fn == "full":
        result = run_full_solve(scenario, **kwargs)
    elif solve_fn == "warm_stop":
        result = run_warm_stop(scenario, **kwargs)
    elif solve_fn == "pruned":
        result = run_pruned_solve(scenario, **kwargs)
    else:
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Unknown solve function: {solve_fn}")
        result = None

    elapsed = time.perf_counter() - start
    return result, round(elapsed, 2)


def is_pruning_noop(
    original_bet_sizes: list[int],
    keep_bet_sizes: list[int],
) -> bool:
    """
    Check whether a pruning decision is effectively a no-op.

    Returns True if the pruned bet sizes are identical to (or a superset of)
    the original bet sizes — meaning the pruned solve would build the same
    tree as the full solve and waste compute.

    Args:
        original_bet_sizes: The scenario's configured bet sizes, e.g. [33, 75].
        keep_bet_sizes: Bet sizes retained after pruning, e.g. [33, 75].

    Returns:
        True if pruning changes nothing (skip the pruned solve).
    """
    return set(keep_bet_sizes) >= set(original_bet_sizes)


def normalize_action_names(
    action_frequencies: dict[str, float],
    pot_size_bb: float,
    effective_stack_bb: float,
    bet_sizes_pct: list[int] | None = None,
) -> dict[str, float]:
    """
    Convert solver chip-based action names to pot-percentage names.

    TexasSolver outputs actions like ``BET 2.000000`` (chip amounts). This
    converts them to human-readable ``BET 33`` (pot percentage) format for
    downstream pruning code and LLM prompts.

    Chip values close to the effective stack are labelled ``ALL-IN``.
    If *bet_sizes_pct* is provided, chip amounts are snapped to the nearest
    configured percentage within ±25 pp.

    Args:
        action_frequencies: Raw action freq dict from extract_action_frequencies().
        pot_size_bb: Pot size in big blinds.
        effective_stack_bb: Effective stack in big blinds.
        bet_sizes_pct: Configured bet sizes (e.g. [33, 75]).

    Returns:
        New dict with normalised action names (same frequencies).
    """
    if pot_size_bb <= 0:
        return dict(action_frequencies)

    normalized: dict[str, float] = {}
    for action, freq in action_frequencies.items():
        parts = action.strip().split()
        if len(parts) == 2 and parts[0].upper() in ("BET", "RAISE"):
            try:
                chips = float(parts[1])
            except ValueError:
                normalized[action] = freq
                continue

            # All-in: chip value within 15 % of effective stack
            if effective_stack_bb > 0 and chips >= effective_stack_bb * 0.85:
                normalized["ALL-IN"] = normalized.get("ALL-IN", 0.0) + freq
                continue

            # Convert to pot percentage
            pct = chips / pot_size_bb * 100.0

            if bet_sizes_pct:
                closest = min(bet_sizes_pct, key=lambda s: abs(s - pct))
                if abs(closest - pct) <= 25:
                    label = f"{parts[0].upper()} {closest}"
                else:
                    label = f"{parts[0].upper()} {round(pct)}"
            else:
                label = f"{parts[0].upper()} {round(pct)}"

            normalized[label] = normalized.get(label, 0.0) + freq
        else:
            normalized[action] = freq

    return normalized


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────


def _validate_solver_json(path: Path) -> bool:
    """Check that a solver output file contains valid, parseable JSON.

    TexasSolver v0.2.0 occasionally produces truncated JSON output files
    (the file is non-empty but json.load() fails with JSONDecodeError).
    This validator lets the retry loop detect the corruption and re-run
    the solver instead of returning a broken file.

    Args:
        path: Path to the solver output JSON file.

    Returns:
        True if the file exists and contains valid JSON, False otherwise.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        if config.DEBUG:
            size_kb = path.stat().st_size / 1024 if path.exists() else 0
            print(f"[SOLVER_HARNESS] Invalid JSON in {path.name} "
                  f"({size_kb:.0f} KB): {exc}")
        return False


def _resolve_output_candidate(
    output_path: Path, result_path: Optional[Path]
) -> Optional[Path]:
    """Find the solver output file from recovery, expected path, or run_solver return.

    Does NOT validate JSON — caller must check _validate_solver_json() on the
    returned path before accepting it.

    Returns:
        Path to the candidate output file, or None if no file found.
    """
    recovered = _recover_solver_output(output_path)
    if recovered is not None:
        return recovered
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    if result_path is not None and result_path.exists():
        return result_path
    return None


def _clean_stale_output(desired_output: Path) -> None:
    """Remove any stale solver output file from both the solver CWD and _work/.

    Prevents file collisions when re-running spots: a stale file left over from
    a prior solve could be mistakenly recovered by _recover_solver_output().
    """
    solver_cwd = Path(config.SOLVER_BINARY_PATH).parent
    filename = desired_output.name

    for stale in [solver_cwd / filename, desired_output]:
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass


def _patch_output_path(input_path: Path, desired_output: Path) -> None:
    """
    Rewrite the dump_result line in the solver input file to use a simple
    filename. TexasSolver writes dump_result relative to its own CWD
    (the binary's parent directory), and does NOT support absolute paths
    with forward slashes on Windows. We use just the filename here,
    then _recover_solver_output() moves the file to the desired location.
    """
    output_filename = desired_output.name  # e.g. "output_full_0.json"
    lines = input_path.read_text(encoding="utf-8").splitlines()
    patched = []
    for line in lines:
        if line.strip().startswith("dump_result"):
            patched.append(f"dump_result {output_filename}")
        else:
            patched.append(line)
    input_path.write_text("\n".join(patched) + "\n", encoding="utf-8")


def _recover_solver_output(desired_output: Path) -> Optional[Path]:
    """
    After a solver run, locate the output file in the solver's CWD
    (binary parent directory) and move it to the desired location.

    TexasSolver writes dump_result relative to its own CWD. This function
    checks for the file there and moves it to the desired path.

    Returns:
        The desired_output path if file was found and moved, else None.
    """
    solver_cwd = Path(config.SOLVER_BINARY_PATH).parent
    filename = desired_output.name
    solver_output = solver_cwd / filename

    if solver_output.exists() and solver_output.stat().st_size > 0:
        import shutil
        # Ensure destination directory exists
        desired_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(solver_output), str(desired_output))
        if config.DEBUG:
            print(f"[SOLVER_HARNESS] Moved output: {solver_output} → {desired_output}")
        return desired_output

    # Also check config.SOLVER_OUTPUT_FILE as fallback
    if config.SOLVER_OUTPUT_FILE.exists() and config.SOLVER_OUTPUT_FILE.stat().st_size > 0:
        import shutil
        desired_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(config.SOLVER_OUTPUT_FILE), str(desired_output))
        return desired_output

    return None


def _create_pruned_scenario(
    scenario: ScenarioData,
    keep_bet_sizes: list[int],
) -> ScenarioData:
    """
    Create a copy of the scenario with reduced bet sizes.

    Args:
        scenario: Original scenario.
        keep_bet_sizes: List of integer bet size percentages to keep.

    Returns:
        New ScenarioData with pruned bet_sizes_pct.
    """
    from dataclasses import replace
    pruned = replace(scenario, bet_sizes_pct=list(keep_bet_sizes))
    return pruned


def _find_root_action_node(tree: dict) -> Optional[dict]:
    """Find the first action_node in the solver output tree."""
    if tree.get("node_type") == "action_node":
        return tree

    if "childrens" in tree:
        for key, child in tree["childrens"].items():
            result = _find_root_action_node(child)
            if result is not None:
                return result

    if "dealcards" in tree:
        for key, child in tree["dealcards"].items():
            result = _find_root_action_node(child)
            if result is not None:
                return result

    return None


def _load_root_node(output_path: Path) -> Optional[dict]:
    """Load a solver output JSON and return its root action node."""
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            tree = json.load(f)
        return _find_root_action_node(tree)
    except Exception:
        return None
