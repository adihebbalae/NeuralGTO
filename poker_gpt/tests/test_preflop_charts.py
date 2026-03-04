"""
test_preflop_charts.py — Validation tests for the converted Jonathan Little GTO preflop charts.

Tests run against the generated JSON in:
    _dev/TASK_RESULTS/PREFLOP_CHARTS_CONV/jonathan_little_gto.json

Created: 2026-03-01

DOCUMENTATION:
    These are OFFLINE tests — no API keys, no solver binary required.
    Run: python -m pytest poker_gpt/tests/test_preflop_charts.py -v
    The JSON must exist before running (produced by _work/build_preflop_json.py).
"""

import json
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

CHARTS_PATH = (
    pathlib.Path(__file__).parents[2]
    / "_dev"
    / "TASK_RESULTS"
    / "PREFLOP_CHARTS_CONV"
    / "jonathan_little_gto.json"
)

ALL_169_COUNT = 169
VALID_ACTIONS = {"Raise", "Call", "Fold"}
EXPECTED_SOURCE = "jonathan_little"


@pytest.fixture(scope="module")
def charts_data():
    """Load and return the full charts JSON once per module."""
    if not CHARTS_PATH.exists():
        pytest.skip(
            f"Charts JSON not found at {CHARTS_PATH}. "
            "Run _work/build_preflop_json.py first."
        )
    with open(CHARTS_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def charts(charts_data):
    return charts_data["charts"]


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


def test_json_has_required_top_keys(charts_data):
    """Top-level JSON must have metadata and charts keys."""
    assert "metadata" in charts_data, "Missing top-level 'metadata' key"
    assert "charts" in charts_data, "Missing top-level 'charts' key"


def test_metadata_version(charts_data):
    """Metadata version must be 3.0 (this conversion run)."""
    assert charts_data["metadata"].get("version") == "3.0"


def test_total_spots_count(charts):
    """Must have at least 100 spots (9max ~69 + 6max ~17 + 4max ~20)."""
    assert len(charts) >= 100, f"Only {len(charts)} spots — expected >= 100"


# ---------------------------------------------------------------------------
# Per-variant presence tests
# ---------------------------------------------------------------------------


def test_9max_positions_covered(charts):
    """9-max must include all 8 RFI positions and core facing/3bet spots."""
    nine_keys = [k for k in charts if k.startswith("9max_")]
    assert len(nine_keys) >= 30, f"Only {len(nine_keys)} 9max spots"

    rfi_positions = {
        k.split("_")[2]
        for k in nine_keys
        if "_rfi_" in k and "facing" not in k
    }
    expected_rfi = {"UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO", "BTN", "SB"}
    missing = expected_rfi - rfi_positions
    assert not missing, f"9max missing RFI positions: {missing}"


def test_6max_positions_covered(charts):
    """6-max must include LJ/HJ/CO/BTN/SB RFI plus some vs-3bet spots."""
    six_keys = [k for k in charts if k.startswith("6max_")]
    assert len(six_keys) >= 10, f"Only {len(six_keys)} 6max spots"

    rfi_positions = {
        k.split("_")[2]
        for k in six_keys
        if "_rfi_" in k and "facing" not in k
    }
    expected_rfi = {"LJ", "HJ", "CO", "BTN", "SB"}
    missing = expected_rfi - rfi_positions
    assert not missing, f"6max missing RFI positions: {missing}"


def test_4max_positions_present(charts):
    """4-max spots must be present and cover at least CO/BTN/SB positions."""
    four_keys = [k for k in charts if k.startswith("4max_")]
    assert len(four_keys) >= 10, f"Only {len(four_keys)} 4max spots"

    rfi_positions = {
        k.split("_")[2]
        for k in four_keys
        if "_rfi_" in k and "facing" not in k
    }
    expected_rfi = {"CO", "BTN", "SB"}
    missing = expected_rfi - rfi_positions
    assert not missing, f"4max missing RFI positions: {missing}"


# ---------------------------------------------------------------------------
# Hand completeness tests
# ---------------------------------------------------------------------------


def test_all_spots_have_169_hands(charts):
    """Every spot must have exactly 169 hands (full preflop matrix)."""
    bad = [
        (key, len(spot["hands"]))
        for key, spot in charts.items()
        if len(spot.get("hands", {})) != ALL_169_COUNT
    ]
    assert not bad, f"Spots with wrong hand count: {bad[:5]}"


def test_no_missing_hands(charts):
    """Spot-check: AA, KK, AKs, AKo, 72o must exist in every spot."""
    sentinel_hands = ["AA", "KK", "AKs", "AKo", "72o"]
    missing = []
    for key, spot in charts.items():
        hands = spot.get("hands", {})
        for h in sentinel_hands:
            if h not in hands:
                missing.append((key, h))
    assert not missing, f"Missing sentinel hands: {missing[:10]}"


# ---------------------------------------------------------------------------
# Action and frequency tests
# ---------------------------------------------------------------------------


def test_all_actions_are_valid(charts):
    """Every hand entry must have action in {Raise, Call, Fold}."""
    invalid = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            act = entry.get("action")
            if act not in VALID_ACTIONS:
                invalid.append((key, hand, act))
    assert not invalid, f"Invalid actions found: {invalid[:10]}"


def test_frequency_in_range(charts):
    """Every hand's frequency must be in [0.0, 1.0]."""
    out_of_range = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            freq = entry.get("frequency")
            if freq is None or not (0.0 <= freq <= 1.0):
                out_of_range.append((key, hand, freq))
    assert not out_of_range, f"Frequencies out of range: {out_of_range[:10]}"


def test_action_dict_sums_le_one(charts):
    """Sum of action frequencies in 'actions' dict must not exceed 1.0."""
    violations = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            actions = entry.get("actions", {})
            total = round(sum(actions.values()), 6)
            if total > 1.001:
                violations.append((key, hand, total))
    assert not violations, f"Action freq sum > 1.0: {violations[:10]}"


def test_mixed_frequency_sums_to_one_for_pure_actions(charts):
    """Non-borderline hands at frequency=1.0 must have actions summing to 1.0."""
    bad = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            if entry.get("chart_note") == "borderline_mix":
                continue  # borderline hands intentionally split
            freq = entry.get("frequency", 0)
            actions = entry.get("actions", {})
            total = round(sum(actions.values()), 6)
            # Pure actions: frequency=1.0 and actions sum should equal 1.0
            if freq == 1.0 and abs(total - 1.0) > 0.01:
                bad.append((key, hand, freq, total))
    assert not bad, f"Pure-action hands with actions not summing to 1.0: {bad[:10]}"


# ---------------------------------------------------------------------------
# Source labeling tests
# ---------------------------------------------------------------------------


def test_source_labeled_on_all_hands(charts):
    """Every hand entry must have source='jonathan_little'."""
    bad = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            if entry.get("source") != EXPECTED_SOURCE:
                bad.append((key, hand, entry.get("source")))
    assert not bad, f"Wrong/missing source labels: {bad[:10]}"


def test_spot_metadata_has_required_fields(charts):
    """Every spot metadata must have key, variant, situation, hero_position."""
    required = {"key", "variant", "situation", "hero_position"}
    bad = []
    for spot_key, spot in charts.items():
        meta = spot.get("metadata", {})
        missing = required - set(meta.keys())
        if missing:
            bad.append((spot_key, missing))
    assert not bad, f"Spots missing metadata fields: {bad[:5]}"


# ---------------------------------------------------------------------------
# Borderline heuristic tests
# ---------------------------------------------------------------------------


def test_borderline_hands_have_correct_fields(charts):
    """Borderline hands must have frequency=0.5, mixed_with set, frequency_alt set."""
    bad = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            if entry.get("chart_note") != "borderline_mix":
                continue
            if entry.get("frequency") != 0.5:
                bad.append((key, hand, "frequency not 0.5", entry.get("frequency")))
            if not entry.get("mixed_with"):
                bad.append((key, hand, "missing mixed_with"))
            if entry.get("frequency_alt") != 0.5:
                bad.append((key, hand, "frequency_alt not 0.5", entry.get("frequency_alt")))
    assert not bad, f"Malformed borderline hands: {bad[:10]}"


def test_borderline_actions_are_different(charts):
    """Borderline primary action and mixed_with must differ."""
    bad = []
    for key, spot in charts.items():
        for hand, entry in spot["hands"].items():
            if entry.get("chart_note") != "borderline_mix":
                continue
            act = entry.get("action")
            mixed = entry.get("mixed_with")
            if act == mixed:
                bad.append((key, hand, act, mixed))
    assert not bad, f"Borderline hands with same primary and mixed_with action: {bad[:10]}"


def test_reasonable_borderline_count(charts):
    """Borderline hands should be > 0 (heuristic is active) and < 50% of total."""
    total_hands = sum(len(spot["hands"]) for spot in charts.values())
    borderline = sum(
        1
        for spot in charts.values()
        for entry in spot["hands"].values()
        if entry.get("chart_note") == "borderline_mix"
    )
    assert borderline > 0, "No borderline hands found — heuristic may not be running"
    assert borderline < total_hands * 0.5, (
        f"Too many borderline hands: {borderline}/{total_hands}"
    )


# ---------------------------------------------------------------------------
# Key format tests
# ---------------------------------------------------------------------------


def test_no_slash_in_keys(charts):
    """All chart keys must be fully expanded (no / remaining)."""
    bad = [k for k in charts if "/" in k]
    assert not bad, f"Unexpanded combined keys: {bad}"


def test_key_prefix_matches_variant(charts):
    """Key prefix (4max/6max/9max) must match metadata.variant."""
    bad = []
    for key, spot in charts.items():
        meta = spot.get("metadata", {})
        variant = meta.get("variant", "")
        prefix = key.split("_")[0]
        if prefix != variant:
            bad.append((key, prefix, variant))
    assert not bad, f"Key prefix/variant mismatch: {bad[:5]}"
