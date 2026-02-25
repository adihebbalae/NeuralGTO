"""
sanity_checker.py — Strategy Sanity Check via LLM.

After the solver produces a strategy (Step 4), this module checks for
extreme or suspicious outputs (e.g., CHECK 99.9%) and uses Gemini to
evaluate whether the result is reasonable poker strategy or potentially
a solver configuration artifact.

Created: 2026-02-06

DOCUMENTATION:
- Triggered when any single action has >= 92% frequency
- Calls Gemini to evaluate if the extreme frequency is correct GTO
  (e.g., overpairs checking back on dynamic boards) or suspicious
  (e.g., misconfigured ranges or bet sizings)
- Returns a human-readable sanity note that gets included in the advice
"""

from google import genai
from google.genai import types

from poker_gpt.poker_types import ScenarioData, StrategyResult
from poker_gpt import config


# Flag any single action with frequency above this threshold
EXTREME_FREQUENCY_THRESHOLD = 0.92

SANITY_SYSTEM_PROMPT = """You are an expert poker theorist reviewing solver output for correctness.

A GTO solver has been run on a poker hand and produced a strategy with an extreme
frequency for one action. Your job is to evaluate whether this is reasonable.

Sometimes extreme frequencies ARE correct GTO strategy:
- Strong overpairs often check back IP on dynamic/coordinated boards to protect checking range
- Nut hands slow-play on very dry boards (e.g., QQ on 2h 4d 7s)
- Weak hands check/fold at very high frequency when they have no equity
- Range advantage situations where one player bets their entire range
- Low SPR spots where jamming/calling is clearly dominant

Other times extreme results can indicate configuration issues:
- Input ranges too narrow or poorly estimated (e.g., villain's range is only QQ+)
- Bet sizings don't match common game trees (missing small bet option)
- Board doesn't match the street (e.g., flop with 4 cards)
- Stack-to-pot ratio is unrealistic

Your analysis MUST:
1. Start with "✅ REASONABLE:" or "⚠️ REVIEW:" on the first line
2. Explain the poker logic (3-5 sentences max)
3. If reasonable, explain WHY the extreme frequency makes GTO sense
4. If suspicious, suggest what input might be off (ranges, sizings, etc.)
"""


def check_strategy_sanity(
    scenario: ScenarioData,
    strategy: StrategyResult,
) -> str:
    """
    Check if the solver's strategy has extreme frequencies and validate with LLM.

    Args:
        scenario: The parsed poker scenario.
        strategy: The extracted solver strategy for hero's hand.

    Returns:
        A sanity note string. Empty if no extreme frequencies detected.
        Contains LLM analysis if an extreme result was found.
    """
    # Check for extreme frequencies
    extreme_actions = []
    for action, freq in strategy.actions.items():
        if freq >= EXTREME_FREQUENCY_THRESHOLD:
            extreme_actions.append((action, freq))

    if not extreme_actions:
        return ""  # No extreme frequencies — strategy looks normal

    # Build context for LLM review
    action_desc = ", ".join(f"{a} at {f*100:.1f}%" for a, f in extreme_actions)

    context = f"""SOLVER OUTPUT TO REVIEW:

Hero hand: {scenario.hero_hand}
Position: {scenario.hero_position} ({'In Position' if scenario.hero_is_ip else 'Out of Position'})
Board: {scenario.board}
Street: {scenario.current_street}
Pot: {scenario.pot_size_bb:.0f}bb
Effective stack: {scenario.effective_stack_bb:.0f}bb
SPR: {scenario.effective_stack_bb / max(scenario.pot_size_bb, 1):.1f}

Solver strategy for {strategy.hand}:
"""
    for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
        context += f"  {action}: {freq*100:.1f}%\n"

    context += f"""
Range-wide strategy (what the full range does):
"""
    for action, freq in sorted(strategy.range_summary.items(), key=lambda x: -x[1]):
        context += f"  {action}: {freq*100:.1f}%\n"

    context += f"""
EXTREME FREQUENCY DETECTED: {action_desc}

Is this extreme frequency reasonable from a GTO perspective?
Analyze the hand strength, board texture, position, and SPR.
"""

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SANITY_SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )
        note = response.text
        if not note:
            return ""
        return note.strip()
    except Exception as e:
        if config.DEBUG:
            print(f"[SANITY_CHECK] LLM sanity check failed: {e}")
        return ""  # Don't block the pipeline if sanity check fails
