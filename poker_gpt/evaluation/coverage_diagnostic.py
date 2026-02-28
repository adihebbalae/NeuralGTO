"""
coverage_diagnostic.py — Deep diagnostic of PokerBench preflop coverage gaps.

Traces every no-match scenario to its specific failure point in the
lookup pipeline. Outputs structured breakdown for analysis.

Usage:
    python -m poker_gpt.evaluation.coverage_diagnostic
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from poker_gpt.evaluation.pokerbench import load_test_set, PBScenario
from poker_gpt.evaluation.evaluator import (
    _holding_nl_to_cards,
    _parse_pb_preflop_actions,
    _pb_to_scenario,
    _snap_to_tree_size,
    _context_snap_size,
)
from poker_gpt.preflop_lookup import (
    _RANGE_DIR,
    _POSITION_MAP,
    _hand_to_canonical,
    _build_action_prefix,
    _find_decision_node_files,
    _normalize_position,
    lookup_preflop_strategy,
)
from poker_gpt.poker_types import ActionEntry


def diagnose_scenario(scenario: PBScenario) -> dict:
    """Trace a scenario through the full mapping pipeline, returning diagnostic info."""
    diag: dict = {
        "index": scenario.index,
        "hero_pos": scenario.hero_position,
        "hero_holding_nl": scenario.hero_holding,
        "ground_truth": scenario.ground_truth,
        "stage": "unknown",
        "reason": "",
        "matched": False,
    }

    # Stage 1: Hand conversion
    hero_hand = _holding_nl_to_cards(scenario.hero_holding)
    if not hero_hand:
        diag["stage"] = "hand_parse"
        diag["reason"] = f"Cannot parse NL holding: '{scenario.hero_holding}'"
        return diag
    diag["hero_hand"] = hero_hand

    # Stage 2: Position mapping
    hero_pos = scenario.hero_position.upper()
    if not hero_pos or hero_pos == "UNKNOWN":
        diag["stage"] = "position"
        diag["reason"] = f"Unknown position: '{scenario.hero_position}'"
        return diag
    
    norm_pos = _normalize_position(hero_pos)
    if norm_pos is None:
        diag["stage"] = "position"
        diag["reason"] = f"Position not in _POSITION_MAP: '{hero_pos}'"
        return diag
    diag["norm_pos"] = norm_pos

    # Stage 3: Action parsing
    actions = _parse_pb_preflop_actions(scenario.instruction, hero_pos)
    diag["parsed_actions"] = [
        f"{a.position} {a.action} {a.amount_bb if a.amount_bb else ''}" 
        for a in actions
    ]

    # Stage 3b: Check for specific action patterns
    action_str = scenario.instruction.lower()
    has_allin = any(a.action == "allin" for a in actions)
    has_limp = "check" in [a.action for a in actions] or "limp" in action_str
    
    # SB completing (calling instead of raising as first action)
    sb_complete = False
    if actions and actions[0].position == "SB" and actions[0].action == "call":
        sb_complete = True
    
    diag["has_allin"] = has_allin
    diag["has_limp"] = has_limp
    diag["sb_complete"] = sb_complete

    # Stage 4: Canonical hand
    canonical = _hand_to_canonical(hero_hand)
    if canonical is None:
        diag["stage"] = "canonical"
        diag["reason"] = f"Cannot canonicalize: '{hero_hand}'"
        return diag
    diag["canonical"] = canonical

    # Stage 5: Build action prefix
    prefix = _build_action_prefix(actions, norm_pos)
    diag["prefix"] = prefix

    # Stage 6: Find decision node files
    hero_dir = _RANGE_DIR / norm_pos
    if not hero_dir.is_dir():
        diag["stage"] = "no_hero_dir"
        diag["reason"] = f"No directory: {hero_dir}"
        return diag

    node_files = _find_decision_node_files(hero_dir, prefix, norm_pos)
    if not node_files:
        diag["stage"] = "no_files"
        diag["reason"] = f"No files match prefix '{prefix}'"
        
        # Try to explain WHY no files matched
        # List what files ARE available for this position
        all_stems = sorted(set(f.stem for f in hero_dir.rglob("*.txt")))
        
        # Check: does any file start with this prefix?
        matching = [s for s in all_stems if s.startswith(prefix + "_" + norm_pos if prefix else norm_pos)]
        diag["available_prefix_count"] = len(matching)
        
        # What's the closest prefix we DO have?
        # e.g. prefix="CO_2.5bb_BTN_AllIn", do we have "CO_2.5bb_BTN_*"?
        if prefix:
            parts = prefix.split("_")
            # Try progressively shorter prefixes
            for trim in range(len(parts) - 1, 0, -1):
                shorter = "_".join(parts[:trim])
                shorter_matches = [s for s in all_stems if s.startswith(shorter)]
                if shorter_matches:
                    diag["closest_available_prefix"] = shorter
                    diag["closest_prefix_file_count"] = len(shorter_matches)
                    # Show a few example files at this shorter prefix
                    diag["closest_prefix_examples"] = shorter_matches[:5]
                    break
        
        return diag

    diag["stage"] = "matched"
    diag["matched"] = True
    diag["node_files"] = list(node_files.keys())
    
    # Actually run the lookup to see if we get a result
    sd = _pb_to_scenario(scenario)
    if sd:
        result = lookup_preflop_strategy(sd)
        if result:
            diag["best_action"] = result.best_action
            diag["best_freq"] = result.best_action_freq
    
    return diag


def run_diagnostic():
    """Run full diagnostic on all preflop scenarios."""
    print("Loading PokerBench preflop scenarios...")
    scenarios = load_test_set("preflop")
    print(f"Loaded {len(scenarios)} scenarios\n")

    diagnostics = []
    for s in scenarios:
        d = diagnose_scenario(s)
        diagnostics.append(d)

    # ── Split matched vs no-match ──
    matched = [d for d in diagnostics if d["matched"]]
    no_match = [d for d in diagnostics if not d["matched"]]

    print("=" * 70)
    print(f"COVERAGE DIAGNOSTIC: {len(matched)}/{len(diagnostics)} matched "
          f"({len(matched)/len(diagnostics):.1%})")
    print(f"No-match: {len(no_match)}")
    print("=" * 70)

    # ── Breakdown by failure stage ──
    stage_counter = Counter(d["stage"] for d in no_match)
    print("\n--- FAILURE STAGE BREAKDOWN ---")
    for stage, count in stage_counter.most_common():
        print(f"  {stage:25s} {count:4d}  ({count/len(no_match):.1%})")

    # ── For no_files failures, deeper analysis ──
    no_files = [d for d in no_match if d["stage"] == "no_files"]
    if no_files:
        print(f"\n--- NO-FILES BREAKDOWN ({len(no_files)} scenarios) ---")
        
        # Categorize by reason
        categories = defaultdict(list)
        for d in no_files:
            prefix = d.get("prefix", "")
            actions = d.get("parsed_actions", [])
            has_allin = d.get("has_allin", False)
            has_limp = d.get("has_limp", False)
            sb_complete = d.get("sb_complete", False)
            
            if has_allin:
                categories["has_allin"].append(d)
            elif sb_complete or has_limp:
                categories["limp_or_sb_complete"].append(d)
            elif prefix == "":
                categories["empty_prefix_open_spot"].append(d)
            else:
                # Check for multi-caller patterns
                call_count = sum(1 for a in actions if "call" in a.lower())
                if call_count > 1:
                    categories["multi_caller"].append(d)
                else:
                    categories["other_path_mismatch"].append(d)
        
        for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
            print(f"\n  {cat}: {len(items)}")
            
            # Show unique prefixes in this category
            prefix_counts = Counter(d.get("prefix", "(none)") for d in items)
            print(f"    Unique prefixes: {len(prefix_counts)}")
            for pf, cnt in prefix_counts.most_common(15):
                # Show one example instruction for the first occurrence
                example = next(d for d in items if d.get("prefix") == pf)
                pos = example.get("norm_pos", "?")
                print(f"      [{cnt:3d}x] pos={pos} prefix='{pf}'")
                # Show closest available prefix if we have it
                if "closest_available_prefix" in example:
                    print(f"             closest_available='{example['closest_available_prefix']}' "
                          f"({example.get('closest_prefix_file_count', '?')} files)")

    # ── Position breakdown for no-match ──
    print("\n--- NO-MATCH BY POSITION ---")
    pos_counter = Counter(d.get("hero_pos", "?") for d in no_match)
    for pos, cnt in pos_counter.most_common():
        print(f"  {pos:5s} {cnt:4d}")

    # ── Ground truth action distribution for no-match ──
    print("\n--- NO-MATCH GROUND TRUTH ACTIONS ---")
    gt_counter = Counter()
    for d in no_match:
        gt = d.get("ground_truth", "?")
        # Normalize to action category
        if gt.startswith("raise") or gt.startswith("bet"):
            gt_counter["raise"] += 1
        elif gt.startswith("call"):
            gt_counter["call"] += 1
        elif gt.startswith("fold"):
            gt_counter["fold"] += 1
        elif gt.startswith("check"):
            gt_counter["check"] += 1
        else:
            gt_counter[gt] += 1
    for action, cnt in gt_counter.most_common():
        print(f"  {action:10s} {cnt:4d}")

    # ── Show sample instruction text for each category ──
    print("\n--- SAMPLE INSTRUCTIONS (first of each no-match category) ---")
    for d in no_match[:3]:
        print(f"\n  Index {d['index']}: pos={d.get('hero_pos','?')}, "
              f"stage={d['stage']}, prefix='{d.get('prefix','')}'")
        # Find the original scenario to show instruction
        scenario = scenarios[d['index']]
        # First 200 chars of instruction
        inst = scenario.instruction[:300].replace('\n', ' ')
        print(f"  Instruction: {inst}...")
        print(f"  Parsed actions: {d.get('parsed_actions', [])}")
        print(f"  Ground truth: {d.get('ground_truth', '?')}")

    # ── Unique prefix patterns in no-match (for mapping analysis) ──
    print("\n--- ALL UNIQUE PREFIXES IN NO-MATCH (top 30) ---")
    prefix_counts = Counter(d.get("prefix", "(none)") for d in no_match)
    for pf, cnt in prefix_counts.most_common(30):
        # Show hero positions for this prefix
        positions = set(d.get("norm_pos", "?") for d in no_match if d.get("prefix") == pf)
        print(f"  [{cnt:3d}x] prefix='{pf}'  positions={positions}")

    # ── Check: what tree files DO we have? ──
    print("\n--- AVAILABLE TREE STRUCTURE (by position) ---")
    for pos_dir in sorted(_RANGE_DIR.iterdir()):
        if pos_dir.is_dir():
            files = list(pos_dir.rglob("*.txt"))
            # Group by first prefix component
            first_parts = Counter()
            for f in files:
                parts = f.stem.split("_")
                if len(parts) >= 2:
                    first_parts[f"{parts[0]}_{parts[1]}"] += 1
            print(f"\n  {pos_dir.name}/ ({len(files)} files)")
            for fp, cnt in first_parts.most_common(10):
                print(f"    {fp}: {cnt} files")


if __name__ == "__main__":
    run_diagnostic()
