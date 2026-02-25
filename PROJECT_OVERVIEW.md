# PokerGPT: Neuro-Symbolic Poker Advisor

**A revolutionary system combining neural AI with symbolic solvers to deliver mathematically optimal poker advice in natural language.**

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Motivations & Vision](#motivations--vision)
3. [What It Does](#what-it-does)
4. [Current Progress](#current-progress)
5. [Current Challenges](#current-challenges)
6. [Technical Architecture](#technical-architecture)
7. [Eventual Goals & Roadmap](#eventual-goals--roadmap)
8. [How to Use](#how-to-use)

---

## Project Overview

**PokerGPT** is a hybrid AI system that transforms natural language poker hand descriptions into **mathematically optimal advice** by combining two complementary AI approaches:

- **Neural (Google Gemini)**: Understands natural language, estimates player ranges, and translates AI recommendations into clear coaching advice
- **Symbolic (TexasSolver)**: Computes Game Theory Optimal (GTO) strategies using Counterfactual Regret Minimization (CFR)

### The Core Problem It Solves

Poker players face a fundamental challenge: **How do I play optimally in a complex hand?**

Traditional poker tools require:
1. Manual scenario setup (positions, ranges, board, stacks)
2. Deep technical knowledge of poker solvers
3. Interpretation of numerical strategy tables

**PokerGPT** simplifies this to:
```
User: "I have QQ on the button, UTG raises to 4bb..."
        ↓
System: [parses] → [solves] → [explains]
        ↓
Advice: "Raise to 12bb. This puts optimal pressure on UTG's range..."
```

---

## Motivations & Vision

### Why Build This?

**Problem 1: GTO Solvers Are Hard to Use**
- Solvers like TexasSolver are powerful but require technical setup
- Users must manually format ranges, boards, and positions
- Output is numerical data, not actionable advice for humans

**Problem 2: LLM-Only Poker Advice Is Unreliable**
- Gemini/ChatGPT can give reasonable poker intuition
- But they lack the mathematical rigor of GTO-based decisions
- They can't reason about complex frequency-dependent strategies

**Problem 3: Gap Between AI and Practical Poker**
- Professional poker trainers solve hands manually
- This process is slow (10+ minutes per hand)
- There's no real-time decision support for learning

### The Vision

**Democratize access to mathematically optimal poker education** by combining:
- **AI Understanding** (Gemini's natural language processing)
- **Mathematical Optimality** (TexasSolver's GTO algorithms)
- **Accessibility** (Clear advice format, 3 speed/accuracy modes)

This enables:
- Poker players to learn from 10-second quick approximations
- Serious learners to study 4-minute precision solutions
- Poker educators to scale personalized coaching

---

## What It Does

### The Pipeline: 5 Steps

```
STEP 1: NL Parser (Gemini)
    Input:  "I have QQ on the button, UTG raises to 4bb in a 6-max game..."
    Output: {hero_hand: "QQ", hero_position: "BTN", board: "", ...}

STEP 2: Solver Input Generator (Python)
    Input:  ScenarioData
    Output: TexasSolver command file (set_pot, set_board, set_range_*, etc.)

STEP 3: Solver Executor (TexasSolver Binary)
    Input:  solver_input.txt
    Output: output_result.json (full game tree + strategies)

STEP 4: Strategy Extractor (Python)
    Input:  output_result.json
    Output: {hand: "QQ", actions: {Raise: 0.78, Fold: 0.22}, ...}

STEP 5: NL Advisor (Gemini)
    Input:  Original question + strategy data
    Output: "Based on the solver, you should raise to 12bb because..."
```

### Key Features

✅ **Three Speed/Accuracy Modes**
- **Fast Mode** (~10s): LLM-only via Gemini's poker knowledge
- **Default Mode** (~1-2 min): Solver at 2% accuracy, balanced quality
- **Pro Mode** (~4-6 min): Solver at 0.3% accuracy, tournament-grade precision

✅ **Dual Interface**
- **Web UI** (Streamlit): Interactive, visual, user-friendly
- **CLI**: Command-line for scripting and batch analysis

✅ **Intelligent Fallback**
- If solver binary unavailable → automatically use Gemini-only mode
- If scenario is preflop → Gemini with poker-theory prompting
- Never fails; quality degrades gracefully

✅ **Intelligent Caching**
- Solver results are expensive to compute
- System caches outputs by scenario hash
- Identical scenarios are answered instantly

✅ **Sanity Checking**
- LLM reviews solver output for extreme frequencies
- Flags counter-intuitive strategies with explanations
- Helps users understand unusual (but correct) decisions

### Current Capabilities

**What Works Well:**
- Heads-up postflop spots (2-player, flop/turn/river)
- Common positions (UTG, MP, CO, BTN, SB, BB)
- Standard stack depths (20bb to 300bb)
- Texas Hold'em 6-max and full-ring games

**What's Limited:**
- Preflop analysis (handled by Gemini fallback, not solved)
- Multi-way pots (solver is 2-player only, uses fallback)
- Shortdeck poker (available in TexasSolver, not yet integrated)
- Non-standard situations (blind steals, final table dynamics)

---

## Current Progress

### What's Implemented ✓

#### Core Pipeline (Feb 6, 2026)
- ✅ NL Parser using Google Gemini (replaced OpenAI)
- ✅ Solver input generator with proper TexasSolver command format
- ✅ Solver executor as Python subprocess with timeout handling
- ✅ Strategy extractor for navigating JSON output trees
- ✅ NL Advisor for converting solver output to human language
- ✅ GPT-only fallback for when solver unavailable

#### Infrastructure
- ✅ Configuration management (.env-based, environment variables)
- ✅ Result caching (hash-based, persistent)
- ✅ Sanity checking via Gemini review
- ✅ Error handling with informative messages
- ✅ Debug mode for troubleshooting

#### User Interfaces
- ✅ Interactive CLI with mode switching
- ✅ Single-query CLI mode (for scripting)
- ✅ Streamlit web UI with visual design
- ✅ Three analysis modes (Fast/Default/Pro)
- ✅ Progress indicators for long-running solves

#### Testing & Documentation
- ✅ 6 offline unit tests (all passing)
- ✅ API integration tests
- ✅ Comprehensive README with quick start
- ✅ Architecture documentation (POKERGPT_ARCHITECTURE.md)
- ✅ Solver reference guide (TEXASSOLVER_REFERENCE.md)
- ✅ Full changelog with migration notes

#### Security
- ✅ API key management via .env (never committed to git)
- ✅ Sanitized example config (.env.example)
- ✅ Removed leaked OpenAI keys from history

### Development Milestones

| Date | Milestone | Status |
|------|-----------|--------|
| 2026-02-06 | Initial architecture design | ✅ Complete |
| 2026-02-06 | TexasSolver codebase analysis | ✅ Complete |
| 2026-02-06 | Core pipeline implementation | ✅ Complete |
| 2026-02-06 | Google Gemini migration | ✅ Complete |
| 2026-02-06 | Solver binary integration | ✅ Complete |
| 2026-02-06 | Web UI (Streamlit) | ✅ Complete |
| 2026-02-06 | Caching system | ✅ Complete |
| 2026-02-06 | Sanity checking | ✅ Complete |

---

## Current Challenges

### Technical Challenges

#### 1. **Range Estimation via LLM**
**Challenge:** Converting natural language hand descriptions (e.g., "UTG raises to 4bb") into valid TexasSolver-compatible range strings.

**Why It's Hard:**
- Ranges are position-dependent (UTG raises differently than BTN)
- Stack depths affect ranges significantly
- Game context affects interpretations (tournament vs cash)
- Gemini must understand poker terminology and generate precise range syntax

**Current Approach:**
- System prompt with deep poker knowledge
- Few-shot examples in prompt
- Fallback to sensible defaults if parsing is ambiguous

**Remaining Issues:**
- Occasional range misestimation in unusual spots
- Non-standard positions (e.g., "hijack +1") sometimes misinterpreted
- Complex multi-action sequences are harder to parse

#### 2. **Solver Output Navigation**
**Challenge:** The solver outputs a complete game tree; we need to find the exact decision node the user asked about.

**Why It's Hard:**
- Game tree is large and nested
- Must correctly track action sequences (raise/call/fold)
- Must distinguish between action nodes and chance nodes (board runouts)

**Current Approach:**
- Recursive tree traversal based on action sequence
- Cache decision nodes by action pattern

**Remaining Issues:**
- All-in situations create complex branching
- Must handle cases where user describes action vaguely

#### 3. **Multi-Way Pot Limitation**
**Challenge:** TexasSolver is fundamentally a 2-player solver.

**Why It's Hard:**
- 3+ player spots are exponentially more complex
- Open-source solvers don't widely support multi-way

**Current Approach:**
- System automatically falls back to Gemini for 3+ player spots
- User gets quick (but less accurate) approximation advice

**Limitation:** This is architectural; solving it would require:
- Using a different solver (e.g., GTO+ for 3-way)
- Building our own multi-way solver (not feasible)

#### 4. **Preflop Analysis**
**Challenge:** Solvers handle postflop; preflop requires different analysis.

**Why It's Hard:**
- Preflop decisions depend on complex Nash equilibrium reasoning
- Board texture unknown; must reason about distributions
- Stack depths heavily influence preflop ranges

**Current Approach:**
- Detect preflop scenarios
- Use Gemini with enhanced poker-theory prompting
- This is actually reasonable because preflop is more intuitive than postflop

**Limitation:** Users get GPT-quality advice, not GTO-solved advice

#### 5. **Solver Timeout & Performance**
**Challenge:** Solving accurately takes time (up to 6 minutes for Pro mode).

**Why It's Hard:**
- CFR algorithm is iterative; accuracy requires more iterations
- Each iteration involves traversing the game tree
- Higher accuracy = longer computation

**Current Approach:**
- Three modes with different accuracy/time tradeoffs
- Intelligent caching prevents redundant solves
- Web UI shows progress indicators

**Remaining Issues:**
- 6 minutes is not "real-time" for live decision support
- Some spots timeout despite 5-minute limit
- No early stopping / approximate convergence detection

### UX/Product Challenges

#### 1. **User Expectation Management**
**Challenge:** Users expect "instant GTO advice" like online poker sites.

**Reality:**
- Accurate solver output takes 1-6 minutes
- Free API usage has quotas
- Users unfamiliar with GTO might not understand the output

**Current Approach:**
- Clear mode descriptions (Fast vs Default vs Pro)
- Progress updates during solving
- Explanatory advice text

**Remaining Issues:**
- First-time users often pick "Pro" and wait 6 minutes
- Some users expect real-time table analysis
- Gemini sometimes gives verbose explanations (token cost)

#### 2. **Poker Knowledge Requirement**
**Challenge:** Users must understand basic poker terms to ask good questions.

**Why It's Hard:**
- "UTG", "SPR", "polar", "compressed" are technical terms
- Non-poker players can't use the system
- Different game variants have different terminology

**Current Approach:**
- Friendly prompts and error messages
- Example questions in UI
- Documentation with terminology guide

**Remaining Issues:**
- Some users give very vague descriptions
- Gemini sometimes misinterprets ambiguous input
- Error messages could be more educational

#### 3. **Gemini API Quota & Cost**
**Challenge:** Even free tier has usage limits.

**Why It's Hard:**
- Gemini API quota varies by account
- Each pipeline run (especially pro mode) consumes tokens
- Multiple Gemini calls per solve (parser + advisor + sanity check)

**Current Approach:**
- Monitor API errors
- Provide clear quota exceeded messages
- Caching prevents redundant calls

**Remaining Issues:**
- No built-in quota monitoring
- Cost scales with heavy usage
- No option to use offline models yet

### Architectural Challenges

#### 1. **Two-Part LLM Pipeline**
**Challenge:** Strategy extraction requires two Gemini calls (parsing + advice).

**Why It's Hard:**
- More API calls = higher latency and cost
- Must ensure parser output feeds correctly into solver input

**Current Approach:**
- Isolate LLM calls in separate modules
- Validate at each step

**Remaining Issues:**
- Parser errors can cascade to solver errors
- No automatic recovery from parser misparse

#### 2. **Windows-Only Solver Binary**
**Challenge:** TexasSolver Windows binary is the only one we have.

**Why It's Hard:**
- Project is currently Windows-only
- Linux/Mac users can't use solver mode
- Deployment on cloud servers (often Linux) is limited

**Current Approach:**
- Document solver download from GitHub
- System works in fallback mode on any OS

**Remaining Issues:**
- Would need Linux binary for broader deployment

---

## Technical Architecture

### System Design

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interfaces                       │
│  ┌────────────────────────┬──────────────────────────────┐  │
│  │  Streamlit Web UI      │   CLI (Interactive + Batch)  │  │
│  └────────────┬───────────┴──────────────┬───────────────┘  │
│               │                          │                   │
└───────────────┼──────────────────────────┼───────────────────┘
                │                          │
┌───────────────▼──────────────────────────▼───────────────────┐
│                    Pipeline Orchestrator                       │
│                      (main.py)                                │
│   - Validates input                                           │
│   - Applies analysis mode preset (Fast/Default/Pro)          │
│   - Manages error handling and fallback                      │
│   - Coordinates all 5 steps                                  │
└───────────┬──────────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  STEP 1: NL Parser (Gemini)                           │
    │  - Loads parser_system.txt prompt                     │
    │  - Extracts: hand, position, board, pot, stacks      │
    │  - Estimates villain ranges                          │
    │  - Output: ScenarioData (JSON-serialized)            │
    └───────┬───────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  CACHE LOOKUP                                         │
    │  - Hash scenario                                      │
    │  - Check _cache/ directory                           │
    │  - If hit: skip to Step 5 (advisor only)            │
    └───────┬──────────┬───────────────────────────────────┘
            │          │
       (hit)│          │(miss)
            │          └─────────────┐
            │                        │
    ┌───────▼────────────────────────▼───────────────────────┐
    │  STEP 2: Solver Input Generator                        │
    │  - Converts ScenarioData to TexasSolver commands      │
    │  - Maps positions to IP/OOP                           │
    │  - Generates range syntax                             │
    │  - Output: solver_input.txt                           │
    └───────┬───────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  STEP 3: Solver Executor                              │
    │  - Spawns console_solver.exe subprocess              │
    │  - Monitors timeout + output                         │
    │  - Handles errors gracefully                         │
    │  - Output: output_result.json                        │
    │  - On failure: fall back to Gemini-only              │
    └───────┬───────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  CACHE STORE                                          │
    │  - Save output_result.json to _cache/                │
    │  - Key by scenario hash                              │
    └───────┬───────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  STEP 4: Strategy Extractor + Sanity Checker          │
    │  - Navigate JSON tree to decision node               │
    │  - Extract frequencies for hero's hand               │
    │  - Compute range-wide summary                        │
    │  - LLM reviews for extreme frequencies               │
    │  - Output: StrategyResult                            │
    └───────┬───────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  STEP 5: NL Advisor (Gemini)                          │
    │  - Loads advisor_system.txt prompt                    │
    │  - Formats strategy data as user message              │
    │  - Generates natural language advice                 │
    │  - References sanity check if available              │
    │  - Output: Advice string                             │
    └───────┬───────────────────────────────────────────────┘
            │
    ┌───────▼───────────────────────────────────────────────┐
    │  Return Advice + Metadata                             │
    │  - Advice text                                        │
    │  - Confidence (source: solver vs Gemini)             │
    │  - Execution time                                    │
    │  - Debug info (if requested)                         │
    └───────────────────────────────────────────────────────┘
```

### Core Components

| Component | Role | Language | Key Files |
|-----------|------|----------|-----------|
| **NL Parser** | Converts user text → structured scenario | Python + Gemini | `nl_parser.py` |
| **Solver Input Gen** | Scenario → TexasSolver command file | Python | `solver_input.py` |
| **Solver Executor** | Runs binary, manages subprocess | Python | `solver_runner.py` |
| **Strategy Extractor** | Parses JSON, navigates tree | Python | `strategy_extractor.py` |
| **NL Advisor** | Strategy → natural language | Python + Gemini | `nl_advisor.py` |
| **Sanity Checker** | Reviews extreme frequencies | Python + Gemini | `sanity_checker.py` |
| **Cache Manager** | Stores/retrieves solver results | Python | `cache.py` |
| **Configuration** | Paths, API keys, settings | Python | `config.py` |

### Data Flow

```python
# Main data structures
ScenarioData:
    hero_hand: str          # "QQ"
    hero_position: str      # "BTN"
    hero_is_ip: bool        # True/False
    board: str              # "Ts9d4h" or ""
    current_street: str     # "preflop", "flop", "turn", "river"
    pot_size_bb: float      # 20.0
    effective_stack_bb: float  # 100.0
    villain_range: str      # "22+, AK, AQ"
    actions_history: list   # [{"action": "raise", "size": "4bb"}, ...]

StrategyResult:
    hand: str               # "QQ"
    source: str             # "solver" or "gemini"
    best_action: str        # "Raise"
    best_action_freq: float # 0.78
    actions: dict          # {"Raise": 0.78, "Fold": 0.22}
    range_summary: dict    # {"Raise": 0.65, "Fold": 0.35}
```

### Key Design Decisions

1. **File-based Solver I/O**: Use console binary's text interface, not DLL integration
   - More portable, no compilation needed
   - Easy to debug (can inspect input/output files)
   - Standard practice for TexasSolver

2. **Dual LLM Calls**: Parser + Advisor for modularity
   - Parser is specialized for structured extraction
   - Advisor is specialized for explanation
   - Allows swapping models independently

3. **Graceful Fallback**: Never fail completely
   - Solver unavailable → use Gemini
   - Parser error → use defaults
   - API quota exceeded → clear error message

4. **Caching by Hash**: Avoid redundant solves
   - Hash all scenario parameters
   - Persistent cache in `_cache/` directory
   - Instant repeat answers

---

## Eventual Goals & Roadmap

### Phase 2: Enhanced Solver Capabilities (Q1-Q2 2026)

**Goal:** Expand solver analysis beyond heads-up postflop.

**Initiatives:**
- [ ] **Preflop Solving** — Integrate or build preflop solver
  - Option 1: OpenFold (open-source preflop solver)
  - Option 2: Pre-computed GTO charts in database
  - Challenge: Requires handling 1326 hands × game variants
  - Timeline: 2-3 weeks

- [ ] **Multi-way Pot Support** — Handle 3+ player spots
  - Option 1: Use GTO+ API if available
  - Option 2: Separate multi-way solver integration
  - Challenge: Exponential complexity, few good open solvers
  - Timeline: 4-6 weeks

- [ ] **Shortdeck Poker** — Enable shortdeck mode
  - Already supported by TexasSolver
  - Just need UI/config updates
  - Timeline: 1 week

- [ ] **Custom Game Trees** — Let users define custom bet sizes/board textures
  - Currently limited to solver's predefined tree files
  - Timeline: 2-3 weeks

### Phase 3: Multi-Platform & Performance (Q2-Q3 2026)

**Goal:** Make PokerGPT accessible and fast everywhere.

**Initiatives:**
- [ ] **Linux/Mac Support** — Build/port TexasSolver solver binary
  - Download or build open-source solvers
  - Update CI/CD for multi-platform
  - Timeline: 2-3 weeks

- [ ] **Cloud Deployment** — Host on cloud infrastructure
  - Streamlit Cloud or AWS Lambda
  - API endpoint for mobile apps
  - Timeline: 2-3 weeks

- [ ] **Performance Optimization**
  - [ ] Parallel solving for multiple hands
  - [ ] GPU acceleration if applicable
  - [ ] Early stopping / convergence detection
  - Timeline: 3-4 weeks

- [ ] **Offline Mode** — Run without API calls
  - Pre-computed strategy database
  - Local fallback LLM (e.g., Ollama)
  - Timeline: 4-6 weeks

### Phase 4: Poker Learning Platform (Q3-Q4 2026)

**Goal:** Transform from tool to comprehensive learning system.

**Initiatives:**
- [ ] **Hand History Analysis** — Analyze full poker sessions
  - Import from PokerTracker / Hold'em Manager
  - Surface mistakes vs GTO
  - Timeline: 3-4 weeks

- [ ] **Training Mode** — Quiz-based learning
  - Generate quiz questions on strategy concepts
  - Spaced repetition of tough spots
  - Leaderboards / achievement tracking
  - Timeline: 4-6 weeks

- [ ] **Range Visualization** — Interactive range charts
  - Display hand frequencies visually
  - Compare user range vs GTO range
  - Timeline: 2-3 weeks

- [ ] **Poker Coach Integration** — Marketplace for coaches
  - Coaches can annotate strategies
  - Students can ask instructor questions
  - Timeline: 6-8 weeks

### Phase 5: Advanced AI Features (Q4 2026 - Q1 2027)

**Goal:** Leverage modern AI for deeper insights.

**Initiatives:**
- [ ] **Game Plan Analysis** — Understand opponent adjustments
  - "What if opponent folds too much?"
  - Sensitivity analysis on ranges
  - Counter-strategy recommendations
  - Timeline: 4-6 weeks

- [ ] **Live Table Advisor** (Research Phase)
  - Real-time advice during play (outside casino restrictions)
  - Voice interface
  - Challenge: Ethical considerations
  - Timeline: 8-12 weeks

- [ ] **Fault Tolerance Training** — Learn exploitative adjustments
  - Identify when to deviate from GTO
  - Exploit specific opponent tendencies
  - Timeline: 3-4 weeks

### Phase 6: Ecosystem & Monetization (2027+)

**Goal:** Build sustainable business & community.

**Initiatives:**
- [ ] **API for 3rd Parties** — Let coaches/tools integrate
  - RESTful API with rate limiting
  - Premium tier pricing
  - Timeline: 2-3 weeks

- [ ] **Mobile App** — iOS/Android version
  - Native UI optimized for phone
  - Offline capabilities
  - Timeline: 8-12 weeks

- [ ] **Premium Tiers**
  - Free: 5 analyses/day, Fast mode only
  - Pro: Unlimited, all modes, priority queue
  - Team: Multiple users, admin panel
  - Timeline: Ongoing

- [ ] **Community Features**
  - Forums for strategy discussion
  - User-submitted hand databases
  - Leaderboards by position/hand type
  - Timeline: 6-8 weeks

### Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Solver Dependency** | Limited to TexasSolver capabilities | Explore alternative solvers (GTO+, PioSOLVER if open-source) |
| **LLM Unreliability** | Parser/advisor errors cascade | Comprehensive error handling, user feedback loops |
| **API Quota/Cost** | Limits free usage; revenue dependency | Implement offline models, rate limiting |
| **Poker Knowledge Gap** | Users don't understand output | Better UX, glossaries, video tutorials |
| **Solver Training Time** | Not truly "real-time" | Precomputation, approximation methods, GPU |
| **Regulatory Issues** | Some jurisdictions restrict poker AI | Use in education only, clear disclaimers |

---

## How to Use

### Quick Start

1. **Install**
   ```bash
   git clone <repo>
   cd neus_nlhe
   pip install -r requirements.txt
   ```

2. **Configure**
   ```bash
   # Edit .env with your Gemini API key
   # Get free key at: https://aistudio.google.com/apikey
   notepad .env
   ```

3. **Run Web UI**
   ```bash
   streamlit run poker_gpt/web_app.py
   ```
   Opens at `http://localhost:8501`

### CLI Usage

```bash
# Interactive mode
python -m poker_gpt.main

# Single query
python -m poker_gpt.main --query "I have QQ on the button..."

# Choose mode
python -m poker_gpt.main --mode pro --query "..."

# Debug output
POKERGPT_DEBUG=true python -m poker_gpt.main
```

### Example Queries

**Good Query:**
> "I have QQ on the button in a 6-max game, 100bb effective. UTG raises to 4bb. What should I do?"

Provides: Position, hand, stack depth, action preceding → enough for solver

**Vague Query:**
> "What do I do with QQ?"

System will ask for more context or use Gemini approximation

---

## Summary

**PokerGPT** is a working hybrid AI system that delivers GTO-based poker advice in natural language. It combines the strengths of neural networks (understanding, explanation) with symbolic solvers (mathematical optimality).

**Current State:** Functional for heads-up postflop analysis; gracefully degrades for preflop, multi-way, and unsupported variants.

**Key Challenges:** Solver portability (Windows-only), multi-way complexity, performance (still takes 1-6 minutes).

**Vision:** Become the comprehensive poker learning platform, making GTO analysis accessible to everyone.

---

**Last Updated:** February 17, 2026  
**Status:** Active Development  
**Maintainer:** PokerGPT Team
