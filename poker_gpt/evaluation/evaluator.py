"""
evaluator.py — PokerBench evaluation runner for NeuralGTO.

Runs the NeuralGTO pipeline (or LLM-only baseline) against PokerBench
scenarios and computes accuracy metrics. Designed for both paper results
and ongoing quality tracking.

Created: 2026-02-27

DOCUMENTATION:
    Three evaluation modes:
    1. "gemini_direct" — Send PokerBench instruction direct to Gemini, ask
       for optimal action. This is the LLM baseline for the paper.
    2. "neuralgto_fast" — Run through full NeuralGTO pipeline in fast mode
       (LLM-only with NeuralGTO's enhanced prompting + range estimation).
    3. "neuralgto_solver" — Full pipeline with TexasSolver (postflop only,
       very slow — use small samples).

    Usage:
        from poker_gpt.evaluation.evaluator import run_evaluation
        results = run_evaluation(
            mode="gemini_direct",
            split="preflop",
            limit=100,
        )
        print(results.summary())
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types

from poker_gpt import config
from poker_gpt.evaluation.pokerbench import (
    PBScenario,
    action_matches,
    load_test_set,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Result of evaluating a single PokerBench scenario.

    Attributes:
        scenario: The original PokerBench scenario.
        predicted_action: The action predicted by NeuralGTO / Gemini.
        predicted_raw: Raw model output text.
        correct: Whether the prediction matches ground truth.
        latency_s: Time taken in seconds.
        error: Error message if prediction failed.
    """
    scenario: PBScenario
    predicted_action: str = ""
    predicted_raw: str = ""
    correct: bool = False
    latency_s: float = 0.0
    error: str = ""


@dataclass
class EvalReport:
    """Aggregated evaluation report.

    Attributes:
        mode: Evaluation mode used.
        split: Dataset split evaluated.
        results: Individual evaluation results.
        total: Total scenarios evaluated.
        correct: Number of correct predictions.
        errors: Number of scenarios that errored.
        accuracy: Overall accuracy (0.0 - 1.0).
        by_street: Accuracy breakdown by street.
        by_action: Accuracy breakdown by ground truth action category.
        by_position: Accuracy breakdown by hero position.
        confusion: Confusion matrix as {true_cat: {pred_cat: count}}.
        total_time_s: Total wall clock time.
        mean_latency_s: Mean per-scenario latency.
    """
    mode: str = ""
    split: str = ""
    results: list[EvalResult] = field(default_factory=list)
    total: int = 0
    correct: int = 0
    errors: int = 0
    accuracy: float = 0.0
    by_street: dict[str, dict] = field(default_factory=dict)
    by_action: dict[str, dict] = field(default_factory=dict)
    by_position: dict[str, dict] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    total_time_s: float = 0.0
    mean_latency_s: float = 0.0

    def summary(self) -> str:
        """Return a human-readable summary of the evaluation."""
        lines = [
            f"=== PokerBench Evaluation Report ===",
            f"Mode: {self.mode}",
            f"Split: {self.split}",
            f"Total: {self.total}  Correct: {self.correct}  "
            f"Errors: {self.errors}",
            f"Accuracy: {self.accuracy:.1%}",
            f"Time: {self.total_time_s:.1f}s  "
            f"Mean latency: {self.mean_latency_s:.2f}s",
            "",
            "--- By Street ---",
        ]
        for street, stats in sorted(self.by_street.items()):
            lines.append(
                f"  {street:10s}: {stats['correct']}/{stats['total']} "
                f"= {stats['accuracy']:.1%}"
            )
        lines.append("")
        lines.append("--- By Ground Truth Action ---")
        for action, stats in sorted(self.by_action.items()):
            lines.append(
                f"  {action:10s}: {stats['correct']}/{stats['total']} "
                f"= {stats['accuracy']:.1%}"
            )
        lines.append("")
        lines.append("--- By Position ---")
        for pos, stats in sorted(self.by_position.items()):
            lines.append(
                f"  {pos:6s}: {stats['correct']}/{stats['total']} "
                f"= {stats['accuracy']:.1%}"
            )
        lines.append("")
        lines.append("--- Confusion Matrix ---")
        all_cats = sorted(
            {c for row in self.confusion.values() for c in row}
            | set(self.confusion.keys())
        )
        header = "           " + "  ".join(f"{c:>8s}" for c in all_cats)
        lines.append(header)
        for true_cat in all_cats:
            row = self.confusion.get(true_cat, {})
            cells = "  ".join(f"{row.get(c, 0):8d}" for c in all_cats)
            lines.append(f"  {true_cat:>8s}: {cells}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (excludes individual results)."""
        return {
            "mode": self.mode,
            "split": self.split,
            "total": self.total,
            "correct": self.correct,
            "errors": self.errors,
            "accuracy": self.accuracy,
            "by_street": self.by_street,
            "by_action": self.by_action,
            "by_position": self.by_position,
            "confusion": self.confusion,
            "total_time_s": self.total_time_s,
            "mean_latency_s": self.mean_latency_s,
        }


# ---------------------------------------------------------------------------
# Gemini direct evaluation
# ---------------------------------------------------------------------------

_DIRECT_SYSTEM_PROMPT = """You are a poker decision engine. Given a No Limit Texas Hold'em game scenario, output ONLY the optimal action.

Rules:
- Output exactly one of: check, call, fold, raise <amount>, or bet <amount>
- Use lowercase
- If raising or betting, include the amount in chips (e.g. "raise 12" or "bet 5")
- Do NOT explain your reasoning
- Do NOT include any other text

Example outputs:
check
call
fold
raise 11
bet 4"""


def _normalize_prediction(raw: str) -> tuple[str, str]:
    """Normalize a raw model output to an action category.

    Handles common Gemini output variations: "Call", "I would fold",
    "The optimal action is check", markdown formatting, etc.

    Args:
        raw: Raw model output text.

    Returns:
        Tuple of (action_category, cleaned_raw).
    """
    text = raw.strip().lower()
    # Strip markdown bold/italic
    text = re.sub(r"[*_`]", "", text)
    # Strip common prefixes
    text = re.sub(
        r"^(the optimal action is|my action is|i would|i should|action:)\s*",
        "",
        text,
    )
    text = text.strip().rstrip(".")

    parts = text.split()
    if not parts:
        return ("unknown", raw)

    action = parts[0]
    if action in ("check", "call", "fold", "raise", "bet"):
        return (action, text)

    # Fuzzy matching for common variations
    for keyword in ("fold", "call", "check", "raise", "bet"):
        if keyword in text:
            return (keyword, text)

    return ("unknown", raw)


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


# ---------------------------------------------------------------------------
# NeuralGTO pipeline evaluation (fast mode)
# ---------------------------------------------------------------------------

_NEURALGTO_EVAL_SYSTEM_PROMPT = """You are a GTO poker advisor. Given a poker scenario, determine the single optimal action.

You have deep knowledge of:
- GTO opening ranges for 6-max NLHE (100bb deep)
- Preflop raise/3bet/4bet strategies by position
- Postflop strategies: c-betting, check-raising, barreling, bluff-catching
- Pot odds, implied odds, equity realization
- Range advantage, nut advantage, board texture analysis
- Blocker effects and range construction principles

Output ONLY the action — one of: check, call, fold, raise <amount>, or bet <amount>
Use lowercase. Include bet/raise amounts in chips.
Do NOT explain."""


def _predict_neuralgto_fast(
    scenario: PBScenario,
    client: genai.Client,
) -> tuple[str, str]:
    """Get NeuralGTO fast-mode prediction (enhanced LLM prompting).

    Uses NeuralGTO's poker-theory-enhanced system prompt instead of
    vanilla Gemini. This measures the value of better prompting.

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
            system_instruction=_NEURALGTO_EVAL_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=1024,
        ),
    )
    raw = response.text.strip().lower() if response.text else ""
    return _normalize_prediction(raw)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(
    results: list[EvalResult],
    mode: str,
    split: str,
    total_time: float,
) -> EvalReport:
    """Aggregate individual results into an EvalReport.

    Args:
        results: List of EvalResult objects.
        mode: Evaluation mode name.
        split: Dataset split name.
        total_time: Total wall clock time in seconds.

    Returns:
        Populated EvalReport.
    """
    report = EvalReport(mode=mode, split=split)
    report.results = results
    report.total = len(results)
    report.correct = sum(1 for r in results if r.correct)
    report.errors = sum(1 for r in results if r.error)
    report.accuracy = report.correct / max(report.total, 1)
    report.total_time_s = total_time
    report.mean_latency_s = (
        sum(r.latency_s for r in results) / max(report.total, 1)
    )

    # By street
    streets: dict[str, list[EvalResult]] = {}
    for r in results:
        streets.setdefault(r.scenario.street, []).append(r)
    for street, rs in streets.items():
        correct = sum(1 for r in rs if r.correct)
        report.by_street[street] = {
            "total": len(rs),
            "correct": correct,
            "accuracy": correct / max(len(rs), 1),
        }

    # By ground truth action
    actions: dict[str, list[EvalResult]] = {}
    for r in results:
        cat = r.scenario.action_category
        # Merge bet+raise into "aggression" for reporting
        if cat in ("bet", "raise"):
            cat = "bet/raise"
        actions.setdefault(cat, []).append(r)
    for action, rs in actions.items():
        correct = sum(1 for r in rs if r.correct)
        report.by_action[action] = {
            "total": len(rs),
            "correct": correct,
            "accuracy": correct / max(len(rs), 1),
        }

    # By position
    positions: dict[str, list[EvalResult]] = {}
    for r in results:
        positions.setdefault(r.scenario.hero_position, []).append(r)
    for pos, rs in positions.items():
        correct = sum(1 for r in rs if r.correct)
        report.by_position[pos] = {
            "total": len(rs),
            "correct": correct,
            "accuracy": correct / max(len(rs), 1),
        }

    # Confusion matrix
    confusion: dict[str, dict[str, int]] = {}
    for r in results:
        if r.error:
            continue
        true_cat = r.scenario.action_category
        pred_cat = r.predicted_action
        # Normalize
        if true_cat in ("bet", "raise"):
            true_cat = "bet/raise"
        if pred_cat in ("bet", "raise"):
            pred_cat = "bet/raise"
        row = confusion.setdefault(true_cat, {})
        row[pred_cat] = row.get(pred_cat, 0) + 1
    report.confusion = confusion

    return report


# ---------------------------------------------------------------------------
# Main evaluation runner
# ---------------------------------------------------------------------------

def run_evaluation(
    mode: Literal["gemini_direct", "neuralgto_fast"] = "gemini_direct",
    split: Literal["preflop", "postflop", "all"] = "all",
    limit: int | None = None,
    progress_callback: callable | None = None,
    save_results: bool = True,
) -> EvalReport:
    """Run PokerBench evaluation.

    Downloads test data on first call, runs predictions via Gemini API,
    and computes accuracy metrics.

    Args:
        mode: Evaluation mode.
            "gemini_direct" — Vanilla Gemini (LLM baseline for paper).
            "neuralgto_fast" — Enhanced poker-theory prompting.
        split: Dataset split to evaluate.
        limit: Max scenarios to evaluate (for quick tests).
        progress_callback: Optional callable(current, total, result) for
            progress updates.
        save_results: Whether to save results JSON to _data/pokerbench/.

    Returns:
        EvalReport with all metrics.
    """
    from dotenv import load_dotenv
    load_dotenv(override=True)
    # Re-read the key in case .env was updated
    api_key = config.GEMINI_API_KEY

    logger.info("Loading PokerBench %s test set...", split)
    scenarios = load_test_set(split, limit=limit)
    logger.info("Loaded %d scenarios", len(scenarios))

    client = genai.Client(api_key=api_key)

    predict_fn = {
        "gemini_direct": _predict_gemini_direct,
        "neuralgto_fast": _predict_neuralgto_fast,
    }.get(mode)

    if predict_fn is None:
        raise ValueError(f"Unknown evaluation mode: {mode!r}")

    results: list[EvalResult] = []
    start_time = time.time()

    for i, scenario in enumerate(scenarios):
        t0 = time.time()
        result = EvalResult(scenario=scenario)

        try:
            action_cat, raw = predict_fn(scenario, client)
            result.predicted_action = action_cat
            result.predicted_raw = raw
            result.correct = action_matches(raw, scenario.ground_truth)
        except Exception as e:
            result.error = str(e)
            logger.warning("Error on scenario %d: %s", i, e)

        result.latency_s = time.time() - t0
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(scenarios), result)

        # Rate limiting: ~15 RPM for free tier, ~60 RPM for paid
        # Be conservative — 0.5s between calls
        if i < len(scenarios) - 1:
            time.sleep(0.5)

    total_time = time.time() - start_time
    report = _aggregate(results, mode, split, total_time)

    if save_results:
        _save_report(report)

    return report


def _save_report(report: EvalReport) -> None:
    """Save evaluation report to JSON file.

    Args:
        report: The evaluation report to save.
    """
    save_dir = Path(__file__).resolve().parent.parent.parent / "_data" / "pokerbench"
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"eval_{report.mode}_{report.split}_{timestamp}.json"
    filepath = save_dir / filename

    # Save report summary + per-scenario details
    data = report.to_dict()
    data["detailed_results"] = [
        {
            "index": r.scenario.index,
            "street": r.scenario.street,
            "position": r.scenario.hero_position,
            "ground_truth": r.scenario.ground_truth,
            "predicted": r.predicted_raw,
            "correct": r.correct,
            "latency_s": round(r.latency_s, 3),
            "error": r.error,
        }
        for r in report.results
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved evaluation report to %s", filepath)
