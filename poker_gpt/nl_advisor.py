"""
nl_advisor.py — Step 5: Strategy → Natural Language Advice.

Uses Google Gemini to convert the solver's strategy output into clear,
actionable poker advice in natural language.

Also provides an LLM-only fallback when the solver binary is not available.

Created: 2026-02-06
Updated: 2026-02-06 — Replaced OpenAI with Google Gemini

DOCUMENTATION:
- Input: Original user question + StrategyResult from strategy_extractor.py
- Output: Natural language poker advice string
- The advisor_system.txt prompt guides the model to be a good poker coach
- Fallback mode uses Gemini alone (no solver) with enhanced poker-theory prompting
"""

import json
from pathlib import Path
from google import genai
from google.genai import types

from poker_gpt.poker_types import ScenarioData, StrategyResult
from poker_gpt import config


def _load_advisor_prompt() -> str:
    """Load the advisor system prompt."""
    prompt_path = Path(__file__).parent / "prompts" / "advisor_system.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_advice(
    user_input: str,
    scenario: ScenarioData,
    strategy: StrategyResult,
    sanity_note: str = "",
    opponent_notes: str = "",
    spot_frequency_text: str = "",
) -> str:
    """
    Generate natural language poker advice from solver strategy.
    
    Args:
        user_input: The original natural language question from the user.
        scenario: The parsed scenario data.
        strategy: The extracted solver strategy for hero's hand.
        sanity_note: Optional sanity check note about extreme frequencies.
        opponent_notes: Optional description of villain tendencies (e.g. "calling
            station", "aggro maniac", "nit who folds too much"). When provided, the
            advisor will resolve the GTO mixed strategy into a concrete exploitative
            action recommendation.
        spot_frequency_text: Optional pre-formatted spot frequency data block
            from spot_frequency.format_spot_frequency_for_advisor().
        
    Returns:
        Natural language advice string.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    system_prompt = _load_advisor_prompt()
    
    # Build the context message with all the data
    context = _build_context_message(user_input, scenario, strategy, sanity_note, opponent_notes, spot_frequency_text)
    
    if config.DEBUG:
        print(f"[NL_ADVISOR] Context message:\n{context[:500]}...")
    
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,  # Slightly more creative for advice
                max_output_tokens=8192,
            ),
        )
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "429" in error_msg:
            raise RuntimeError(
                "Gemini API quota exceeded. Check your billing at "
                "https://console.cloud.google.com/billing"
            )
        raise RuntimeError(f"Gemini API call failed: {e}")
    
    advice = response.text
    if not advice:
        raise RuntimeError(
            "Gemini returned an empty response. The request may have been "
            "blocked by safety filters or the model returned no candidates."
        )
    
    if config.DEBUG:
        print(f"[NL_ADVISOR] Generated advice ({len(advice)} chars)")
    
    return advice


def _build_context_message(
    user_input: str,
    scenario: ScenarioData,
    strategy: StrategyResult,
    sanity_note: str = "",
    opponent_notes: str = "",
    spot_frequency_text: str = "",
) -> str:
    """Build the user message that includes all context for the advisor."""
    
    # Format action frequencies nicely
    actions_str = ""
    for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
        pct = freq * 100
        actions_str += f"  - {action}: {pct:.1f}%\n"
    
    range_str = ""
    for action, freq in sorted(strategy.range_summary.items(), key=lambda x: -x[1]):
        pct = freq * 100
        range_str += f"  - {action}: {pct:.1f}%\n"
    
    msg = f"""ORIGINAL QUESTION FROM USER:
{user_input}

PARSED SCENARIO:
- Hero's hand: {scenario.hero_hand}
- Hero's position: {scenario.hero_position} ({'In Position' if scenario.hero_is_ip else 'Out of Position'})
- Board: {scenario.board}
- Street: {scenario.current_street}
- Pot size: {scenario.pot_size_bb:.0f} BB
- Effective stack remaining: {scenario.effective_stack_bb:.0f} BB
- SPR (Stack-to-Pot Ratio): {scenario.effective_stack_bb / max(scenario.pot_size_bb, 1):.1f}

SOLVER STRATEGY FOR {strategy.hand}:
{actions_str}
Best action: {strategy.best_action} ({strategy.best_action_freq * 100:.1f}%)

RANGE-WIDE STRATEGY (what the entire range does here):
{range_str}

Data source: {strategy.source}

NOTE TO ADVISOR: If data source is "solver" or "solver_cached", this strategy
is computed by the TexasSolver CFR engine and is mathematically grounded.
If data source is "gpt_fallback" or "preflop_lookup", note this in your response.
"""
    if sanity_note:
        msg += f"""
SANITY CHECK NOTE:
The following analysis was done on the solver output. Take it into account
when formulating advice — if the sanity check flagged something, acknowledge
the extreme frequency and explain why it may be correct or what to watch for.

{sanity_note}
"""
    if opponent_notes:
        # Check if this contains pool-level tendencies (live game prep mode)
        if "[POOL TENDENCIES" in opponent_notes:
            # Split into individual villain notes and pool notes
            parts = opponent_notes.split("[POOL TENDENCIES")
            individual_notes = parts[0].strip()
            pool_section = "[POOL TENDENCIES" + parts[1] if len(parts) > 1 else ""

            if individual_notes:
                msg += f"""
VILLAIN TENDENCY NOTES:
The user has described the villain as follows. Use this information in your
"Villain Adjustment" section to recommend a concrete exploitative deviation
from the GTO baseline. Resolve any mixed strategy into a single action.

  \"{individual_notes}\"
"""
            if pool_section:
                msg += f"""
POOL TENDENCY NOTES (LIVE GAME PREP MODE):
The user has described the overall player pool at their table/game. These are
population-level tendencies — not a specific villain but the typical opponent
at this game. Use these to recommend a SESSION-WIDE exploitative strategy.

Frame your advice as: "Against this player pool, the solver's GTO baseline
shifts in the following ways..." Focus on which hands become more/less
profitable to play and which bet sizes exploit the pool's leaks.

  \"{pool_section}\"
"""
        else:
            msg += f"""
VILLAIN TENDENCY NOTES:
The user has described the villain as follows. Use this information in your
"Villain Adjustment" section to recommend a concrete exploitative deviation
from the GTO baseline. Resolve any mixed strategy into a single action.

  \"{opponent_notes}\"
"""
    if spot_frequency_text:
        msg += f"\n{spot_frequency_text}\n"

    msg += "\nPlease provide your advice to the user based on this solver analysis.\n"
    return msg


# ──────────────────────────────────────────────
# Fallback: GPT-Only Mode (no solver)
# ──────────────────────────────────────────────

FALLBACK_SYSTEM_PROMPT = """You are an expert poker advisor who provides GTO-approximated advice.

You don't have access to a solver right now, but you deeply understand solver outputs 
and GTO strategy from years of study. Provide advice that closely matches what a solver 
would recommend.

When giving advice:
1. Consider the player's hand strength relative to the board texture
2. Think about range advantage and nut advantage
3. Consider position (IP vs OOP)
4. Think about stack-to-pot ratio (SPR)
5. Consider bet sizing in terms of pot fractions
6. Give a clear primary recommendation with approximate frequencies
7. Explain your reasoning using poker theory concepts
8. Mention what to do on common runouts

IMPORTANT GUIDELINES:
- Overpairs on dry boards: Usually bet for value (especially IP)
- Draws on wet boards: Consider semi-bluffing  
- Nut hands: Often slow-play on dry boards, fast-play on wet boards
- Weak hands: Check/fold or use as bluffs depending on equity
- Position matters hugely: IP can bet wider, OOP should be more cautious
- SPR affects strategy: Low SPR = more all-ins, High SPR = more street-by-street play

Frame your advice as approximate GTO, noting this is without a solver calculation.
Be honest that exact frequencies would require a solver, but your recommendations 
should be directionally correct.
"""


def generate_fallback_advice(
    user_input: str,
    scenario: ScenarioData,
    opponent_notes: str = "",
) -> str:
    """
    Generate poker advice using GPT alone (no solver).
    Used when the solver binary is not available.
    
    Args:
        user_input: The original natural language question.
        scenario: The parsed scenario data.
        opponent_notes: Optional description of villain tendencies.
        
    Returns:
        Natural language advice string.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    villain_section = ""
    if opponent_notes:
        villain_section = f"""
VILLAIN TENDENCY NOTES:
Use this to provide an exploitative deviation from the GTO baseline.
Resolve any mixed strategy into a single concrete action for this villain.

  \"{opponent_notes}\"
"""

    context = f"""USER'S POKER QUESTION:
{user_input}

PARSED SCENARIO DATA:
- Hero: {scenario.hero_hand} on the {scenario.hero_position}
- Board: {scenario.board}
- Street: {scenario.current_street}
- Pot: {scenario.pot_size_bb:.0f}bb
- Effective stack: {scenario.effective_stack_bb:.0f}bb
- Hero is {'In Position' if scenario.hero_is_ip else 'Out of Position'}
- SPR: {scenario.effective_stack_bb / max(scenario.pot_size_bb, 1):.1f}

OOP range estimate: {scenario.oop_range[:100]}...
IP range estimate: {scenario.ip_range[:100]}...
{villain_section}
Please provide GTO-approximate advice for this spot.
"""
    
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=FALLBACK_SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "429" in error_msg:
            raise RuntimeError(
                "Gemini API quota exceeded. Check your billing at "
                "https://console.cloud.google.com/billing"
            )
        raise RuntimeError(f"Gemini API call failed: {e}")
    
    advice = response.text
    if not advice:
        raise RuntimeError(
            "Gemini returned an empty response. The request may have been "
            "blocked by safety filters or the model returned no candidates."
        )
    
    # Add disclaimer
    advice += (
        "\n\n---\n*Note: This advice is generated without a solver calculation. "
        "For exact GTO frequencies, the TexasSolver engine is needed.*"
    )
    
    return advice
