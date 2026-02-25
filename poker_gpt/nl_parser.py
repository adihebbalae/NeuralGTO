"""
nl_parser.py — Step 1: Natural Language → Structured Scenario.

Uses Google Gemini to parse a natural language poker hand description
into a structured ScenarioData object that can be fed to the solver.

Created: 2026-02-06
Updated: 2026-02-06 — Replaced OpenAI with Google Gemini

DOCUMENTATION:
- Input: A string like "I have QQ on the button, UTG raises to 4bb..."
- Output: ScenarioData dataclass with all fields populated
- The Gemini model estimates ranges based on positions and actions
- Uses the parser_system.txt prompt for consistent output format
"""

import json
import re
from pathlib import Path
from google import genai
from google.genai import types

from poker_gpt.poker_types import ScenarioData, ActionEntry
from poker_gpt import config


def _load_system_prompt() -> str:
    """Load the parser system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent / "prompts" / "parser_system.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def parse_scenario(user_input: str) -> ScenarioData:
    """
    Parse a natural language poker scenario into structured data.
    
    Args:
        user_input: Natural language description of the poker hand.
        
    Returns:
        ScenarioData object with all fields populated.
        
    Raises:
        ValueError: If the GPT response cannot be parsed.
        RuntimeError: If the API call fails.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    system_prompt = _load_system_prompt()
    
    if config.DEBUG:
        print(f"[NL_PARSER] Sending scenario to Gemini: {user_input[:100]}...")
    
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=config.GEMINI_TEMPERATURE,
                response_mime_type="application/json",
                max_output_tokens=8192,
            ),
        )
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "429" in error_msg:
            raise RuntimeError(
                "Gemini API quota exceeded. Check your billing at "
                "https://console.cloud.google.com/billing\n"
                f"Original error: {e}"
            )
        raise RuntimeError(f"Gemini API call failed: {e}")
    
    raw_response = response.text
    if not raw_response:
        raise RuntimeError(
            "Gemini returned an empty response. The request may have been "
            "blocked by safety filters or the model returned no candidates."
        )
    
    if config.DEBUG:
        print(f"[NL_PARSER] Raw Gemini response:\n{raw_response}")
    
    # Parse the JSON response — clean up trailing commas that some models produce
    cleaned = re.sub(r',\s*([}\]])', r'\1', raw_response)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {e}\nRaw: {raw_response}")
    
    # Validate and convert to ScenarioData
    return _dict_to_scenario(data)


def _dict_to_scenario(data: dict) -> ScenarioData:
    """
    Convert the parsed GPT JSON dict to a ScenarioData object.
    Applies validation and defaults.
    """
    # Extract required fields with validation
    hero_hand = data.get("hero_hand", "")
    if not hero_hand or len(hero_hand) != 4:
        raise ValueError(f"Invalid hero hand: '{hero_hand}'. Expected 4-char format like 'QhQd'.")
    
    hero_position = data.get("hero_position", "BTN").upper()
    board = data.get("board", "")
    current_street = data.get("current_street", "flop")
    
    # Validate board matches street
    if board:
        board_cards = [c.strip() for c in board.split(",")]
        expected_cards = {"flop": 3, "turn": 4, "river": 5}
        if len(board_cards) != expected_cards.get(current_street, 3):
            # Adjust street based on board
            if len(board_cards) == 3:
                current_street = "flop"
            elif len(board_cards) == 4:
                current_street = "turn"
            elif len(board_cards) == 5:
                current_street = "river"
    
    pot_size_bb = float(data.get("pot_size_bb", 6.0))
    effective_stack_bb = float(data.get("effective_stack_bb", 100.0))
    hero_is_ip = bool(data.get("hero_is_ip", True))
    
    # Ranges
    oop_range = data.get("oop_range", "")
    ip_range = data.get("ip_range", "")
    
    if not oop_range or not ip_range:
        raise ValueError("Gemini failed to generate player ranges.")
    
    # Action history
    action_history = []
    for entry in data.get("action_history", []):
        action_history.append(ActionEntry(
            position=entry.get("position", ""),
            action=entry.get("action", ""),
            amount_bb=entry.get("amount_bb"),
            street=entry.get("street", "preflop"),
        ))
    
    # Build ScenarioData
    scenario = ScenarioData(
        hero_hand=hero_hand,
        hero_position=hero_position,
        board=board,
        pot_size_bb=pot_size_bb,
        effective_stack_bb=effective_stack_bb,
        current_street=current_street,
        oop_range=oop_range,
        ip_range=ip_range,
        hero_is_ip=hero_is_ip,
        action_history=action_history,
        num_players_preflop=int(data.get("num_players_to_flop", 2)),
        stack_depth_bb=float(data.get("stack_depth_bb", 100.0)),
    )
    
    if config.DEBUG:
        print(f"[NL_PARSER] Parsed scenario:")
        print(f"  Hero: {scenario.hero_hand} ({scenario.hero_position})")
        print(f"  Board: {scenario.board}")
        print(f"  Pot: {scenario.pot_size_bb}bb, Stack: {scenario.effective_stack_bb}bb")
        print(f"  Hero is {'IP' if scenario.hero_is_ip else 'OOP'}")
        print(f"  Street: {scenario.current_street}")
    
    return scenario
