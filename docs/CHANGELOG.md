# PokerGPT Development Changelog

## 2026-02-06 — Gemini Migration & Solver Binary Setup

### LLM Backend: OpenAI → Google Gemini
- Replaced `openai` SDK with `google-genai` SDK across all modules
- Updated `config.py`: `OPENAI_API_KEY` → `GEMINI_API_KEY`, `OPENAI_MODEL` → `GEMINI_MODEL`
- Updated `nl_parser.py`: Uses `genai.Client` + `generate_content()` with JSON response mode
- Updated `nl_advisor.py`: Both `generate_advice()` and `generate_fallback_advice()` use Gemini
- Updated `main.py`: User-facing strings now reference Gemini
- Updated `test_pipeline.py`: API key checks reference `GEMINI_API_KEY`
- Updated `.env.example`: Sanitized (removed leaked API keys!), now shows Gemini config
- Updated `requirements.txt`: `openai>=1.0.0` → `google-genai>=1.0.0`
- Model: `gemini-2.0-flash` (fast, free tier available)

### Solver Binary
- Downloaded TexasSolver v0.2.0 Windows release from GitHub
- Binary: `solver_bin/TexasSolver-v0.2.0-Windows/console_solver.exe`
- Configured `SOLVER_BINARY_PATH` and `SOLVER_RESOURCES_PATH` in `.env`
- Added `solver_bin/` and zip file to `.gitignore`

### Security Fix
- CRITICAL: `.env.example` previously contained actual API keys (both OpenAI and Gemini)
- Sanitized `.env.example` to use placeholder values only
- Removed `OPENAI_API_KEY` from `.env` (no longer needed)

### Documentation
- Updated README.md, POKERGPT_ARCHITECTURE.md, CHANGELOG.md to reference Gemini
- Updated all module docstrings with "Replaced OpenAI with Google Gemini" note

### Testing
- All 6 offline tests pass after migration
- API tests verified with Gemini API key

---

## 2026-02-06 — Initial Implementation

### Codebase Analysis
- Studied the complete TexasSolver repository (C++ source code)
- Analyzed the command-line interface (CommandLineTool.cpp)
- Documented solver command format (set_pot, set_board, set_range_*, etc.)
- Analyzed the JSON output structure (action_node, chance_node, strategy format)
- Identified console binary as the best integration method
- Documented findings in `docs/TEXASSOLVER_REFERENCE.md`

### Architecture Design
- Designed 5-step neuro-symbolic pipeline:
  1. NL Parser (GPT) → turns natural language into structured data
  2. Solver Input Generator (Python) → creates solver command file
  3. Solver Executor (Python subprocess) → runs TexasSolver binary
  4. Strategy Extractor (Python) → parses solver JSON output
  5. NL Advisor (GPT) → converts strategy to human-readable advice
- Added GPT-only fallback mode for when solver binary is unavailable
- Documented architecture in `docs/POKERGPT_ARCHITECTURE.md`

### Files Created
```
poker_gpt/__init__.py              — Package init
poker_gpt/main.py                  — Entry point, CLI, pipeline orchestrator
poker_gpt/config.py                — Configuration management (paths, API keys, settings)
poker_gpt/poker_types.py           — Data classes: ScenarioData, StrategyResult, ActionEntry
poker_gpt/range_utils.py           — Range utilities, default GTO ranges by position
poker_gpt/nl_parser.py             — Step 1: NL → structured scenario (Gemini)
poker_gpt/solver_input.py          — Step 2: Scenario → TexasSolver command file
poker_gpt/solver_runner.py         — Step 3: Run solver binary as subprocess
poker_gpt/strategy_extractor.py    — Step 4: Parse solver JSON → StrategyResult
poker_gpt/nl_advisor.py            — Step 5: Strategy → NL advice (Gemini) + fallback
poker_gpt/prompts/parser_system.txt   — System prompt for NL parsing
poker_gpt/prompts/advisor_system.txt  — System prompt for advice generation
poker_gpt/tests/__init__.py           — Test package
poker_gpt/tests/test_pipeline.py      — Offline + API pipeline tests
poker_gpt/tests/sample_solver_output.json — Mock solver output for testing
.env.example                       — Template for environment variables
.gitignore                         — Updated with Python/PokerGPT patterns
requirements.txt                   — Python dependencies (google-genai, python-dotenv)
README.md                          — Comprehensive project README
docs/TEXASSOLVER_REFERENCE.md      — TexasSolver documentation
docs/POKERGPT_ARCHITECTURE.md      — Architecture design document
docs/CHANGELOG.md                  — This file
```

### Environment Setup
- Created Python 3.13 virtual environment (.venv)
- Installed packages: google-genai, python-dotenv
- Configured .env with GEMINI_API_KEY

### Testing
- All 6 offline tests pass:
  - hand_to_solver_combos (pair, suited, offsuit, specific)
  - is_valid_card (validation)
  - get_position_relative (IP/OOP determination)
  - normalize_hand_for_lookup (hand key normalization)
  - solver_input_generation (generates 36 commands, validates content)
  - strategy_extraction (extracts from sample JSON, finds correct hands for OOP and IP)
- API tests require active Gemini API key (previously OpenAI with quota issues)

### Known Issues / Next Steps
1. **LLM API**: Migrated from OpenAI to Google Gemini (free tier available).
   Previous OpenAI key had insufficient quota (429 error).
2. **Solver binary**: The TexasSolver console binary needs to be obtained. Options:
   - Download from GitHub releases (v0.2.0 Windows package)
   - Build from the console branch using MinGW + CMake
   - The system works in GPT-only fallback mode without it
3. **Multi-way pots**: Current implementation handles heads-up (2-player) spots only.
   The solver is fundamentally a 2-player solver. For 3+ player spots, the
   GPT fallback mode handles the approximation.
4. **Preflop solving**: The solver works on postflop spots only (flop/turn/river).
   Preflop advice is handled entirely by GPT in the current design.
