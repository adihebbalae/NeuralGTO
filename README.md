# PokerGPT — Neuro-Symbolic Poker Advisor

A system that combines **Google Gemini** (neural/probabilistic) with **TexasSolver** (symbolic/deterministic) to provide mathematically optimal poker advice in natural language.

## How It Works

```
"I have QQ on the button..."    →    Gemini parses    →    Solver computes    →    Gemini explains    →    "You should bet 2/3 pot..."
```

1. **You describe a poker hand** in natural language  
2. **Gemini parses** it into structured solver input (positions, ranges, board, pot, stacks)  
3. **TexasSolver runs CFR** to find the Game Theory Optimal strategy  
4. **Python extracts** the strategy for your specific hand  
5. **Gemini translates** the solver output into clear coaching advice  

If the solver binary isn't available, the system falls back to LLM-only mode with enhanced poker-theory prompting.

## Quick Start

### 1. Install Dependencies
```bash
cd neus_nlhe
pip install -r requirements.txt
```

### 2. Set Your Gemini API Key
```bash
# Edit .env and add your Gemini API key
# Get a key at: https://aistudio.google.com/apikey
notepad .env
```

### 3. Run PokerGPT

#### Web UI (Recommended)
```bash
streamlit run poker_gpt/web_app.py
```
Opens a web interface at http://localhost:8501 with three modes:
- **Fast** — LLM-only (~10s), quick GTO-approximate advice
- **Default** — Solver at 2% accuracy (~1-2 min), good approximation  
- **Pro** — Solver at 0.3% accuracy (~4-6 min), precise GTO solution

#### CLI
```bash
# Interactive mode (default solver mode)
python -m poker_gpt.main

# Single query with mode selection
python -m poker_gpt.main --mode fast --query "Quick preflop question..."
python -m poker_gpt.main --mode pro --query "I have QQ on the button..."

# With debug output
python -m poker_gpt.main --debug
```

In interactive mode, type `mode fast`, `mode default`, or `mode pro` to switch modes.

## Setting Up the Solver

The solver is already set up in `solver_bin/`. If you need to reconfigure or reinstall:

1. Go to [TexasSolver Releases](https://github.com/bupticybee/TexasSolver/releases)
2. Download `TexasSolver-v0.2.0-Windows.zip`
3. Extract `console_solver.exe` + `resources/` into `solver_bin/`
4. Update paths in `.env` if needed

## Project Structure

```
neus_nlhe/
├── .env                          # API key + all configuration
├── requirements.txt              # Python dependencies
├── README.md
├── poker_gpt/                    # Main package
│   ├── main.py                   # Entry point, pipeline orchestrator, analyze_hand()
│   ├── web_app.py                # Streamlit web UI with Fast/Default/Pro modes
│   ├── config.py                 # Configuration + MODE_PRESETS
│   ├── poker_types.py            # Data classes (ScenarioData, StrategyResult, etc.)
│   ├── range_utils.py            # Poker range utilities & default ranges
│   ├── nl_parser.py              # Step 1: NL → structured scenario (Gemini)
│   ├── solver_input.py           # Step 2: Scenario → solver command file
│   ├── solver_runner.py          # Step 3: Execute TexasSolver binary
│   ├── strategy_extractor.py     # Step 4: Parse solver JSON → strategy
│   ├── sanity_checker.py         # Step 4.5: LLM review of extreme frequencies
│   ├── nl_advisor.py             # Step 5: Strategy → NL advice (Gemini)
│   ├── cache.py                  # Solver result caching (hash → JSON)
│   ├── prompts/                  # System prompts for Gemini
│   ├── tests/                    # Offline + API tests
│   ├── _cache/                   # Cached solver outputs (auto-created)
│   └── _work/                    # Runtime working directory (auto-created)
├── solver_bin/                   # TexasSolver v0.2.0 binary + resources
│   └── TexasSolver-v0.2.0-Windows/
│       ├── console_solver.exe
│       ├── resources/            # Compairer data for hand evaluation
│       ├── ranges/               # Default range presets
│       └── parameters/           # Sample solver parameters
└── docs/                         # Architecture, solver reference, changelog
```

## How Each Module Works

### `nl_parser.py` — Natural Language Parser
- Sends the user's poker question to Gemini with a detailed system prompt
- Gemini extracts: hero hand, positions, board, pot, stacks, action history
- Gemini estimates player ranges based on position and actions (the hard part!)
- Returns a `ScenarioData` dataclass

### `solver_input.py` — Solver Input Generator
- Converts `ScenarioData` into TexasSolver's command format
- Generates commands: `set_pot`, `set_board`, `set_range_oop`, `set_range_ip`, etc.
- Configures bet sizes, tree building, and solver parameters
- Writes to a `.txt` file that the solver binary reads

### `solver_runner.py` — Solver Executor
- Runs the TexasSolver console binary as a subprocess
- Passes the input file and resources directory
- Handles timeouts, errors, and missing binary gracefully
- Returns the path to the output JSON file

### `strategy_extractor.py` — Strategy Extractor
- Parses the solver's JSON output (recursive tree of action/chance nodes)
- Navigates to the correct decision point based on hero's position
- Extracts the strategy for hero's specific hand combos
- Computes range-wide summaries for context

### `nl_advisor.py` — Natural Language Advisor
- Sends the original question + solver strategy to Gemini  
- Gemini acts as a poker coach: recommends actions, explains reasoning
- Also provides a fallback mode (LLM-only, no solver needed)

## Example Usage

### Input
```
I have QQ on the button, UTG raises to 4bb, I 3bet to 12bb, 
BB and UTG call. Flop is Ts 9d 4h, checks to me. 
I bet 20bb, and BB goes all in for 85bb, UTG folds. 
What do I do here?
```

### Output (example)
```
🎯 PokerGPT Advice:

**You should call the all-in with QQ here.**

With pocket Queens, you have an overpair on this T♠ 9♦ 4♥ board — one 
of the strongest hands in your range. The solver recommends calling about 
85% of the time and folding only 15%.

Here's why calling is correct:
- QQ is well ahead of BB's value range (sets of TT/99/44, two pair T9)
  and has excellent equity against their bluffs (flush draws, straight draws)
- The pot is offering you roughly 2.5:1 odds, and you only need ~29% equity
- Your overpair has about 55-65% equity against a typical all-in range here

The only concern is sets (TT, 99, 44), but those are only a small fraction 
of BB's range. Against the full polarized range (sets + draws), QQ is a 
clear call.
```

## Running Tests

```bash
# Offline tests (no API key needed)
python -m poker_gpt.tests.test_pipeline

# Full tests including API (needs GEMINI_API_KEY)
python -m poker_gpt.tests.test_pipeline --with-api
```

## Configuration

All configuration is via environment variables (`.env` file):

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | (required) | Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `SOLVER_BINARY_PATH` | `TexasSolver/console.exe` | Path to solver binary |
| `SOLVER_RESOURCES_PATH` | `TexasSolver/resources` | Path to solver resources |
| `SOLVER_THREAD_NUM` | `4` | Solver parallelism |
| `SOLVER_ACCURACY` | `0.5` | Solver accuracy (% of pot) |
| `SOLVER_MAX_ITERATIONS` | `200` | Max CFR iterations |
| `SOLVER_TIMEOUT` | `300` | Solver timeout (seconds) |
| `USE_SOLVER` | `true` | Enable/disable solver |
| `POKERGPT_DEBUG` | `false` | Debug output |

## Architecture Notes

### Why Neuro-Symbolic?
- **Solvers** (symbolic): Mathematically perfect but hard to use — need exact ranges, positions, bet sizes
- **LLMs** (neural): Easy to use but trained on internet poker advice (often wrong)
- **PokerGPT** (hybrid): Uses GPT to bridge the human↔solver interface, gets the best of both

### Range Estimation
The hardest part of the pipeline. When a user says "UTG raises", we need to estimate UTG's range.
Gemini is prompted with standard GTO range charts and poker logic to produce solver-compatible range strings.
The `range_utils.py` module provides default ranges as a reference.

### Solver vs Fallback
When the solver binary is available, the system produces exact GTO strategies.
When it's not, Gemini provides approximate advice based on its poker knowledge.
The output clearly indicates which mode was used.

## Dependencies
- **Python 3.10+**  
- **google-genai** — Google Gemini API client  
- **python-dotenv** — Environment variable management  
- **TexasSolver** — (optional) GTO solver binary  
