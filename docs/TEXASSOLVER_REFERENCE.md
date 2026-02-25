# TexasSolver Reference Guide
> Auto-generated documentation from codebase analysis. Last updated: 2026-02-06

## 1. Overview
TexasSolver is an open-source, high-performance Texas Hold'em and Short Deck poker solver written in C++.
It uses **Counterfactual Regret Minimization (CFR)** — specifically **Discounted CFR (DCFR)** — to compute
Game Theory Optimal (GTO) strategies for postflop spots.

- **License**: AGPL-v3 (free for personal use)
- **Author**: bupticybee (Xuefeng Huang)
- **Frameworks**: Qt 5.1.0 (GUI), MinGW + CMake (console)
- **Platforms**: Windows, macOS, Linux

## 2. How the Solver Works (High Level)
1. **Define the game tree parameters**: pot size, effective stack, board cards, player ranges, bet sizes
2. **Build the game tree**: the solver enumerates all possible action sequences (bet/raise/call/fold/allin/check)
3. **Train via CFR**: iteratively minimizes regret across all information sets (hand combos × decision points)
4. **Output**: a JSON strategy file mapping each hand combo to action frequencies at each decision node

## 3. Console Interface — Command Language
The solver reads commands line-by-line from a text file. Key commands:

| Command | Example | Description |
|---|---|---|
| `set_pot <N>` | `set_pot 50` | Sets the current pot size. Internally sets `ip_commit = oop_commit = N/2` |
| `set_effective_stack <N>` | `set_effective_stack 200` | Sets effective stack (remaining chips behind). Internally `stack = N + ip_commit` |
| `set_board <cards>` | `set_board Qs,Jh,2h` | Board cards comma-separated. 3 cards = flop, 4 = turn, 5 = river |
| `set_range_oop <range>` | `set_range_oop AA,KK,...` | OOP player's range in standard notation with optional weights (e.g., `99:0.75`) |
| `set_range_ip <range>` | `set_range_ip QQ:0.5,...` | IP player's range |
| `set_bet_sizes <params>` | `set_bet_sizes oop,flop,bet,50` | Set bet sizes as % of pot. Format: `player,street,type,size1,size2,...` |
| `set_allin_threshold <N>` | `set_allin_threshold 0.67` | When remaining stack is ≤ threshold × pot, auto-allin |
| `build_tree` | `build_tree` | Build the game tree with current settings |
| `set_thread_num <N>` | `set_thread_num 8` | Number of threads |
| `set_accuracy <N>` | `set_accuracy 0.5` | Target exploitability (% of pot). Lower = more accurate, slower |
| `set_max_iteration <N>` | `set_max_iteration 200` | Max CFR iterations |
| `set_print_interval <N>` | `set_print_interval 10` | Print progress every N iterations |
| `set_use_isomorphism <0|1>` | `set_use_isomorphism 1` | Use suit isomorphism to reduce tree size |
| `start_solve` | `start_solve` | Begin training |
| `set_dump_rounds <N>` | `set_dump_rounds 2` | How many streets deep to dump results |
| `dump_result <file>` | `dump_result output.json` | Save strategy to JSON |

### Bet Size Types
- `bet` — opening bet sizes (% of pot)
- `raise` — raise sizes (% of pot)
- `donk` — donk bet sizes (only for OOP on later streets)
- `allin` — include all-in as an option (no size parameter needed)

### Card Notation
- Ranks: `2,3,4,5,6,7,8,9,T,J,Q,K,A`
- Suits: `c` (clubs), `d` (diamonds), `h` (hearts), `s` (spades)
- Example: `Qs` = Queen of spades, `Th` = Ten of hearts

### Range Notation
- Single hand: `AA`, `AKs` (suited), `AKo` (offsuit)
- With weight: `99:0.75` (75% frequency)
- Comma-separated: `AA,KK,QQ:0.5,AKs,AKo:0.75`
- No weight = 100% frequency (weight 1.0)

## 4. JSON Output Structure
The dumped JSON has a recursive tree structure:

```json
{
  "actions": ["CHECK", "BET 50"],
  "player": 0,          // 0 = OOP, 1 = IP
  "node_type": "action_node",
  "strategy": {
    "strategy": {
      "AhKh": [0.85, 0.15],   // [check_freq, bet_freq]
      "AsKs": [0.80, 0.20],
      ...
    }
  },
  "childrens": {
    "CHECK": { ... },          // subtree after check
    "BET 50": { ... }          // subtree after bet
  }
}
```

### Node Types
- `action_node` — a decision point for a player. Has `actions`, `strategy`, `childrens`, `player`
- `chance_node` — a card deal (turn/river). Has `dealcards`, `deal_number`
- Showdown and Terminal nodes are leaf nodes (not explicitly dumped)

### Strategy Format
- `strategy.strategy` is a dict: keys are hand strings (e.g., `"AhKh"`), values are arrays of floats
- Each float corresponds to the action at the same index in the `actions` array
- Values sum to 1.0 (probability distribution over actions)

## 5. Integration Methods

### A. Command-line input file (simplest, what we'll use)
1. Write a `.txt` file with solver commands
2. Feed it to the console binary: `console.exe -i input.txt -r ./resources -m holdem`
3. Read the output JSON

### B. C FFI / DLL (api.cpp)
- Compile as DLL, call `api(input_file, resource_dir, mode)` from Python via ctypes
- Same as console but callable from other languages

### C. Python bindings (pybind)
- Direct Python API via pybind11 (requires compilation)

## 6. Key Solver Parameters for PokerGPT

### Players
- **OOP** (Out Of Position) = player 0 — acts first postflop
- **IP** (In Position) = player 1 — acts last postflop

### Typical Settings
- `accuracy`: 0.3-0.5% for reasonable speed/quality tradeoff
- `max_iteration`: 100-300
- `thread_num`: match CPU cores
- `use_isomorphism`: 1 (always, saves memory)
- `allin_threshold`: 0.67 (standard)

### Required Resources
- `resources/compairer/card5_dic_sorted.txt` — hand ranking dictionary (2.6M lines)
- `resources/compairer/card5_dic_zipped.bin` — binary version (auto-generated)
- These must exist for the solver to initialize

## 7. File Locations (in our workspace)
```
TexasSolver/
├── src/console.cpp                    — Console entry point
├── src/tools/CommandLineTool.cpp       — Command parser (processes input files)
├── src/runtime/PokerSolver.cpp        — Core solver interface
├── src/solver/PCfrSolver.cpp          — CFR solver + JSON dump logic
├── include/tools/CommandLineTool.h     — Command interface header
├── include/runtime/PokerSolver.h       — Solver API header
├── resources/text/commandline_sample_input.txt — Sample input file
├── resources/compairer/                — Hand comparison data files
├── resources/outputs/                  — Output directory
└── benchmark/benchmark_texassolver.txt — Another sample input
```
