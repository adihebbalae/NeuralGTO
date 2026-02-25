"""
strategy_extractor.py — Step 4: Parse Solver JSON Output.

Reads the TexasSolver output JSON, navigates the game tree to the
decision point, and extracts the strategy for the hero's specific hand.

Created: 2026-02-06

DOCUMENTATION:
- Input: Path to solver output JSON + ScenarioData (to know hero's hand)
- Output: StrategyResult with action frequencies and recommendations
- The JSON has a recursive tree structure with action_node and chance_node types
- We navigate to the ROOT action node (first decision point in solver's tree)
  and extract the strategy for hero's specific hand combos

JSON STRUCTURE REMINDER:
{
    "actions": ["CHECK", "BET 67"],
    "player": 0,        # 0=OOP, 1=IP
    "node_type": "action_node",
    "strategy": {
        "strategy": {
            "QhQd": [0.85, 0.15],  # freq for each action
            ...
        }
    },
    "childrens": { ... }
}
"""

import json
from pathlib import Path
from typing import Optional

from poker_gpt.poker_types import ScenarioData, StrategyResult
from poker_gpt.range_utils import hand_to_solver_combos, normalize_hand_for_lookup
from poker_gpt import config


def extract_strategy(output_file: Path, scenario: ScenarioData) -> StrategyResult:
    """
    Extract the solver's recommended strategy for hero's hand.
    
    Args:
        output_file: Path to the solver's output JSON.
        scenario: The parsed scenario (needed for hero's hand and position info).
        
    Returns:
        StrategyResult with action frequencies and recommendation.
    """
    with open(output_file, "r", encoding="utf-8") as f:
        tree = json.load(f)
    
    if config.DEBUG:
        print(f"[STRATEGY_EXTRACT] Loaded JSON tree. Top-level keys: {list(tree.keys())}")
    
    # Find the root action node (first decision point)
    root_node = _find_root_action_node(tree)
    
    if root_node is None:
        raise ValueError("Could not find an action node in the solver output.")
    
    actions = root_node.get("actions", [])
    player = root_node.get("player", 0)  # 0=OOP, 1=IP
    strategy_data = root_node.get("strategy", {}).get("strategy", {})
    
    if config.DEBUG:
        print(f"[STRATEGY_EXTRACT] Root node: player={player}, actions={actions}")
        print(f"[STRATEGY_EXTRACT] Strategy has {len(strategy_data)} hand entries")
    
    # Determine which player we're looking at
    # player 0 = OOP, player 1 = IP
    hero_player = 1 if scenario.hero_is_ip else 0
    
    # If the root node's player doesn't match hero, we need to navigate deeper
    # The root node is the first to act — in postflop scenarios this is OOP
    target_node = root_node
    if player != hero_player:
        # Hero is not the first to act. We need to find the node where hero acts.
        # This means navigating through the tree following the action history.
        target_node = _navigate_to_hero_node(tree, hero_player, scenario)
        if target_node is None:
            # Fallback: use root node anyway (hero might be first to act in some configs)
            target_node = root_node
    
    actions = target_node.get("actions", [])
    strategy_data = target_node.get("strategy", {}).get("strategy", {})
    
    # Find hero's hand strategy
    hero_hand = scenario.hero_hand
    hand_strategy = _find_hand_strategy(hero_hand, strategy_data)
    
    if hand_strategy is None:
        # Try all combos of the hand
        combos = hand_to_solver_combos(hero_hand[:2] + hero_hand[2:])
        for combo in combos:
            hand_strategy = _find_hand_strategy(combo, strategy_data)
            if hand_strategy is not None:
                hero_hand = combo
                break
    
    if hand_strategy is None:
        raise ValueError(
            f"Could not find hero's hand {scenario.hero_hand} in solver output. "
            f"Available hands (sample): {list(strategy_data.keys())[:10]}"
        )
    
    # Build action frequency dict
    action_freqs = {}
    for i, action_name in enumerate(actions):
        if i < len(hand_strategy):
            action_freqs[action_name] = round(hand_strategy[i], 4)
    
    # Find best action
    best_action = max(action_freqs, key=action_freqs.get) if action_freqs else "CHECK"
    best_freq = action_freqs.get(best_action, 0.0)
    
    # Compute range summary
    range_summary = _compute_range_summary(actions, strategy_data)
    
    result = StrategyResult(
        hand=hero_hand,
        actions=action_freqs,
        best_action=best_action,
        best_action_freq=best_freq,
        range_summary=range_summary,
        raw_node=target_node,
        source="solver",
    )
    
    if config.DEBUG:
        print(f"[STRATEGY_EXTRACT] Hero hand: {hero_hand}")
        print(f"[STRATEGY_EXTRACT] Actions: {action_freqs}")
        print(f"[STRATEGY_EXTRACT] Best: {best_action} ({best_freq:.1%})")
    
    return result


def _find_root_action_node(tree: dict) -> Optional[dict]:
    """Find the first action_node in the tree (root of the strategy)."""
    if tree.get("node_type") == "action_node":
        return tree
    
    # Check childrens
    if "childrens" in tree:
        for key, child in tree["childrens"].items():
            result = _find_root_action_node(child)
            if result is not None:
                return result
    
    # Check dealcards (chance nodes)
    if "dealcards" in tree:
        for key, child in tree["dealcards"].items():
            result = _find_root_action_node(child)
            if result is not None:
                return result
    
    return None


def _navigate_to_hero_node(tree: dict, hero_player: int, scenario: ScenarioData) -> Optional[dict]:
    """
    Navigate the game tree to find a node where it's hero's turn to act.
    
    The solver tree starts at the first postflop decision. If hero is IP
    and OOP checks, we need to find the node after CHECK where it's IP's turn.
    """
    node = _find_root_action_node(tree)
    if node is None:
        return None
    
    # If the root node is already for hero, return it
    if node.get("player") == hero_player:
        return node
    
    # Otherwise, try to navigate via each action in the childrens
    # Common case: OOP checks, and we look at the IP node after CHECK
    childrens = node.get("childrens", {})
    
    # Try "CHECK" first (most common when hero is IP and OOP checks to us)
    for try_action in ["CHECK", "check"]:
        if try_action in childrens:
            child = childrens[try_action]
            if child.get("node_type") == "action_node" and child.get("player") == hero_player:
                return child
            # Try one more level deep
            child_node = _find_player_node(child, hero_player, depth=2)
            if child_node is not None:
                return child_node
    
    # Try all children
    for action_name, child in childrens.items():
        child_node = _find_player_node(child, hero_player, depth=3)
        if child_node is not None:
            return child_node
    
    return None


def _find_player_node(tree: dict, player: int, depth: int = 3) -> Optional[dict]:
    """Find an action_node for the specified player within depth levels."""
    if depth <= 0:
        return None
    
    if tree.get("node_type") == "action_node" and tree.get("player") == player:
        return tree
    
    if "childrens" in tree:
        for key, child in tree["childrens"].items():
            result = _find_player_node(child, player, depth - 1)
            if result is not None:
                return result
    
    return None


def _find_hand_strategy(hand: str, strategy_data: dict) -> Optional[list]:
    """
    Find the strategy for a specific hand in the strategy data.
    Tries multiple key formats since the solver may use different orderings.
    """
    # Direct lookup
    if hand in strategy_data:
        return strategy_data[hand]
    
    # Try reversed card order
    if len(hand) == 4:
        reversed_hand = hand[2:4] + hand[0:2]
        if reversed_hand in strategy_data:
            return strategy_data[reversed_hand]
    
    # Try normalized lookup
    if len(hand) == 4:
        normalized = normalize_hand_for_lookup(hand[0:2], hand[2:4])
        if normalized in strategy_data:
            return strategy_data[normalized]
    
    return None


def _compute_range_summary(actions: list, strategy_data: dict) -> dict:
    """
    Compute the average strategy across all hands in the range.
    This gives a high-level view of what the range does.
    """
    if not strategy_data or not actions:
        return {}
    
    n_actions = len(actions)
    totals = [0.0] * n_actions
    count = 0
    
    for hand, freqs in strategy_data.items():
        for i in range(min(n_actions, len(freqs))):
            totals[i] += freqs[i]
        count += 1
    
    if count == 0:
        return {}
    
    summary = {}
    for i, action_name in enumerate(actions):
        summary[action_name] = round(totals[i] / count, 4)
    
    return summary
