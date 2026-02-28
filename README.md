# NeuralGTO

**Neuro-symbolic poker advisor** — describe a hand in plain English, get mathematically optimal strategy with human-readable explanations.

Combines **Google Gemini** (neural) for natural language understanding with **TexasSolver CFR** (symbolic) for provably optimal game theory solutions. The LLM handles the messy human interface; the solver does the math. Neither alone is sufficient.

> This is a **study tool**, not a real-time bot. Built for post-session review and GTO learning.

---

## Pipeline

```
Plain English ──→ Gemini Parse ──→ TexasSolver CFR ──→ Strategy Extract ──→ Gemini Explain
                  (ScenarioData)   (game tree solve)   (StrategyResult)     (NL advice)
```

| Step | Module | What it does |
|---:|---|---|
| 1 | `nl_parser.py` | NL → `ScenarioData` via Gemini (hand, board, positions, ranges) |
| 2 | `solver_input.py` | `ScenarioData` → TexasSolver command file |
| 3 | `solver_runner.py` | Subprocess executor → `output_result.json` |
| 4 | `strategy_extractor.py` | JSON tree → `StrategyResult` for hero's specific hand |
| 5 | `nl_advisor.py` | `StrategyResult` → coaching advice via Gemini |

If the solver binary isn't available or the spot is preflop, the system falls back gracefully to LLM-only mode with enhanced poker-theory prompting. Output always indicates which mode produced the answer.

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/adihebbalae/NeuralGTO.git
cd NeuralGTO
pip install -r requirements.txt

# 2. Configure (get a key at https://aistudio.google.com/apikey)
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=your-key-here

# 3. Run
streamlit run poker_gpt/web_app.py        # Web UI at localhost:8501
python -m poker_gpt.main                   # Interactive CLI
python -m poker_gpt.main --mode pro --query "I have QQ on the BTN..."
```

### Analysis Modes

| Mode | Solver | Accuracy | Time | Use case |
|---:|:---:|:---:|:---:|---|
| `fast` | No | — | ~10s | Quick LLM-only approximation |
| `default` | Yes | 2% | ~1-2 min | Good GTO approximation |
| `pro` | Yes | 0.3% | ~4-6 min | Precise GTO solution |

CLI commands: `mode fast`, `mode default`, `mode pro` to switch mid-session.

---

## Session 6 Features

- **Trust badge** — every response shows `Powered by TexasSolver CFR` or `Gemini Analysis` so you know the source
- **Table-ready heuristics** — bold one-line "Table Rule" you can memorize and apply live
- **Conversational gap-filling** — CLI detects missing details (hand, position, board) and prompts interactively
- **Live game prep mode** — describe opponent pool tendencies, get session-wide exploitative adjustments
- **Study spot prioritizer** — frequency data shows how often you'll encounter each spot, with study priority labels

---

## Solver Setup

TexasSolver is optional — the system works without it (LLM-only mode).

1. Download from [TexasSolver Releases](https://github.com/bupticybee/TexasSolver/releases) (v0.2.0)
2. Extract into `solver_bin/TexasSolver-v0.2.0-Windows/`
3. Set paths in `.env`:
   ```
   SOLVER_BINARY_PATH=solver_bin/TexasSolver-v0.2.0-Windows/console_solver.exe
   SOLVER_RESOURCES_PATH=solver_bin/TexasSolver-v0.2.0-Windows/resources
   ```

> **Note:** TexasSolver is heads-up postflop only. Preflop and 3+ player spots use Gemini fallback.

---

## Project Structure

```
poker_gpt/
├── main.py                  # Pipeline orchestrator + CLI (analyze_hand())
├── web_app.py               # Streamlit web UI
├── config.py                # All config, env vars, mode presets
├── poker_types.py           # ScenarioData, StrategyResult, ActionEntry
│
├── nl_parser.py             # Step 1: NL → ScenarioData (Gemini)
├── solver_input.py          # Step 2: ScenarioData → solver command file
├── solver_runner.py         # Step 3: Execute TexasSolver subprocess
├── strategy_extractor.py    # Step 4: JSON tree → StrategyResult
├── nl_advisor.py            # Step 5: StrategyResult → NL advice (Gemini)
├── sanity_checker.py        # Step 4.5: LLM review of extreme frequencies
│
├── range_utils.py           # Range math utilities + default GTO ranges
├── range_display.py         # 13×13 hand grid visualization (ASCII + Rich)
├── preflop_lookup.py        # Pre-computed preflop GTO charts
├── spot_frequency.py        # Spot frequency data + study prioritization
├── hand_history.py          # PokerStars/Winamax/GGPoker HH parser
├── cache.py                 # Hash-based persistent solver cache
├── auth.py                  # Lightweight auth + free-tier gating
├── security.py              # Rate limiting + input sanitization
├── validation.py            # Input validation utilities
│
├── prompts/                 # System prompts (advisor_system.txt, parser_system.txt)
├── tests/                   # 124 offline tests (pytest)
├── _cache/                  # Cached solver outputs (auto-created)
└── _work/                   # Runtime solver I/O (auto-created)
```

---

## Example

**Input:**
```
I have QQ on the button, UTG raises to 4bb, I 3bet to 12bb,
BB and UTG call. Flop is Ts 9d 4h, checks to me.
I bet 20bb, and BB goes all in for 85bb, UTG folds.
What do I do here?
```

**Output:**
```
Powered by TexasSolver CFR

You should call the all-in with QQ here.

QQ is an overpair on T♠ 9♦ 4♥ — one of the strongest hands in your
range. The solver recommends calling ~85% and folding ~15%.

Why calling is correct:
• QQ is ahead of BB's value range (sets TT/99/44, two pair T9) and
  has strong equity against draws (flush draws, straight draws)
• Pot odds: ~2.5:1 → you need ~29% equity; QQ has 55-65% here
• Sets are a small fraction of BB's range; against the full polarized
  range, QQ is a clear call

📋 Table Rule: Call — you have an overpair with clean pot odds.
```

---

## Testing

```bash
# All offline tests (no API key or solver binary needed)
python -m pytest poker_gpt/tests/ -v -k "not test_full_pipeline_with_api"

# Integration test (needs GEMINI_API_KEY)
python -m pytest poker_gpt/tests/ -v -k "test_full_pipeline_with_api"
```

124 tests across pipeline logic, preflop lookup, hand history parsing, and Session 6 features.

---

## Configuration

All via environment variables (`.env` file). See `.env.example` for the full template.

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `SOLVER_BINARY_PATH` | — | Path to `console_solver.exe` |
| `SOLVER_RESOURCES_PATH` | — | Path to solver `resources/` dir |
| `SOLVER_THREAD_NUM` | `4` | Solver thread parallelism |
| `SOLVER_TIMEOUT` | `300` | Solver timeout in seconds |
| `USE_SOLVER` | `true` | Enable/disable solver |
| `POKERGPT_DEBUG` | `false` | Verbose debug logging |

---

## Architecture: Why Neuro-Symbolic?

**Solvers alone** are mathematically perfect but require exact inputs — ranges in comma-separated hand notation, precise pot/stack sizes, correct position assignments. No casual user can provide these.

**LLMs alone** can understand natural language but are trained on internet poker advice — a mix of correct theory and recreational-player myths. They hallucinate frequencies and invent plausible-sounding but wrong reasoning.

**NeuralGTO** bridges the gap: Gemini handles the messy NL↔structured-data translation (range estimation, scenario parsing), while TexasSolver provides the mathematically provable strategy. The LLM then explains *why* the solver's answer is correct — blockers, board texture, range balance, equity realization — rather than just stating frequencies.

### Known Limitations

- **Heads-up postflop only** — TexasSolver is a 2-player solver. Multi-way spots fall back to Gemini.
- **Windows binary** — `console_solver.exe` is Windows-only. Linux/Mac support planned via Docker.
- **Preflop** — Solver handles postflop only. Preflop uses pre-computed lookup tables + Gemini fallback.
- **Range estimation** — The hardest unsolved problem. Gemini estimates ranges from position + action history, calibrated against GTO charts in `range_utils.py`.

---

## Research

NeuralGTO is also a research project exploring neuro-symbolic approaches to poker strategy explanation. Target venues: AAAI, AAMAS, NeurIPS Workshop on Games.

**Planned contributions:**
- Semantically-pruned CFR (LLM prunes implausible branches before solving)
- Pairwise HU decomposition for multi-way approximation
- Neural solver approximator for real-time inference

---

## License

MIT

---

## Dependencies

- Python 3.10+
- [google-genai](https://pypi.org/project/google-genai/) — Gemini API client
- [python-dotenv](https://pypi.org/project/python-dotenv/) — env var management
- [Streamlit](https://streamlit.io/) — web UI
- [Rich](https://rich.readthedocs.io/) — CLI formatting
- [TexasSolver](https://github.com/bupticybee/TexasSolver) — *(optional)* CFR solver binary
