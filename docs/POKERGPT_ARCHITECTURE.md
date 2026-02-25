# PokerGPT — Architecture & Design Document
> Neuro-Symbolic Poker Advisor using Google Gemini + TexasSolver
> Created: 2026-02-06 | Updated: 2026-02-06

## Overview
PokerGPT takes a natural language poker hand description, uses GPT to parse it into
structured data, feeds it to the TexasSolver CFR engine, and translates the solver's
mathematically optimal strategy back into plain-English advice.

## Pipeline Diagram
```
┌──────────────────────────────────────────────────────────────────────┐
│  USER: "I have QQ on the button, UTG raises to 4bb..."             │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 1: NL Parser  (Google Gemini)                                │
│  - Extracts: hero hand, positions, board, pot, stacks, actions     │
│  - Estimates villain ranges based on action/position               │
│  - Output: Structured JSON (ScenarioData)                          │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 2: Solver Input Generator  (Python)                          │
│  - Converts ScenarioData → TexasSolver command file                │
│  - Maps positions to OOP/IP                                        │
│  - Formats ranges, board, pot, stacks, bet sizes                  │
│  - Writes solver_input.txt                                         │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 3: Solver Execution  (TexasSolver binary)                    │
│  - Runs: console.exe -i solver_input.txt -r ./resources -m holdem  │
│  - CFR training (100-200 iterations, 0.5% accuracy)                │
│  - Outputs: output_result.json                                     │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 4: Strategy Extractor  (Python)                              │
│  - Loads output_result.json                                        │
│  - Navigates the strategy tree to the decision point               │
│  - Extracts hero's specific hand strategy                          │
│  - Computes aggregate range strategy for context                   │
│  - Output: StrategyResult dict                                     │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 5: NL Advice Generator  (Google Gemini)                      │
│  - Input: original question + solver strategy data                 │
│  - Converts frequencies to clear advice                            │
│  - Explains reasoning (why bet/check/fold at these frequencies)    │
│  - Output: Natural language poker advice                           │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  USER: "With QQ on this Ts9d4h board, the solver recommends..."    │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Range Estimation via LLM
The hardest part of the pipeline is estimating player ranges from natural language.
Gemini is prompted with deep poker knowledge to produce TexasSolver-compatible
range strings based on positions, actions, and stack depths.

### 2. Solver Mode: File-based I/O
We use the console binary's file-based interface (most portable, no compilation needed):
- Write commands to `solver_input.txt`
- Run `console.exe -i solver_input.txt -r ./resources -m holdem`
- Read `output_result.json`

### 3. Fallback: GPT-Only Mode
If the solver binary isn't available, the system falls back to Gemini with an
enhanced poker-theory system prompt. Less accurate but always available.

### 4. Strategy Navigation
The solver outputs a full game tree. We navigate it based on the action sequence
described in the user's scenario to find the right decision node.

## File Structure
```
poker_gpt/
├── __init__.py
├── main.py                  # Entry point / CLI
├── config.py                # Configuration (paths, API keys, defaults)
├── nl_parser.py             # Step 1: NL → structured scenario (Gemini)
├── solver_input.py          # Step 2: Scenario → solver input file
├── solver_runner.py         # Step 3: Execute TexasSolver binary
├── strategy_extractor.py    # Step 4: Parse solver JSON output
├── nl_advisor.py            # Step 5: Strategy → NL advice (Gemini)
├── poker_types.py           # Data classes / types
├── range_utils.py           # Poker range utilities
└── prompts/
    ├── parser_system.txt    # System prompt for NL parsing
    └── advisor_system.txt   # System prompt for advice generation
```

## Dependencies
- Python 3.10+
- google-genai (Google Gemini Python SDK)
- python-dotenv (for API key management)
- TexasSolver console binary (optional, for full solver mode)
