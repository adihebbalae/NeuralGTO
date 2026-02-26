# NeuralGTO — Next Steps Brainstorm
**Last updated:** February 25, 2026

---

## 🎯 Core Differentiator — The "Why" Layer (New Priority)

### The Insight

GTO Wizard and PioSOLVER both give you a grid of numbers.
Neither one ever explains *why* you are doing what you are doing.

> "4bet A5s at 33.5%"

That's what every solver tells you. NeuralGTO should be the first tool that
tells you **why**:

> "A5s is a strong 4bet bluff candidate because it has good blockers to AA/AK
> (the A blocks AA and AK), it has too little equity to call profitably against a
> 3bet range, but enough equity + blocker value to make it preferable over
> pure bluffs like 72o. The 33% frequency balances your 4bet range so you're
> not too bluff-heavy or too value-heavy — making you unexploitable."

That explanation builds a *principle* the player can carry to every future A5s
spot, not just this one. Memorizing frequencies is brittle. Understanding the
*why* transfers.

---

### The GTO vs. Exploitative Problem

GTO is a Nash Equilibrium strategy — it assumes your opponent is *also* playing
perfectly. In that world:
- You cannot be exploited
- But you also minimally exploit your opponent
- You "lose the minimum" but you don't "win the maximum"

In practice, almost no live or online player plays GTO. The field folds too
often, doesn't bluff enough, value bets too thin, or never 3bets light. Against
*those* players, pure GTO actually leaves significant EV on the table.

**The real edge in poker is knowing when to deviate from GTO and how.**

---

### The Feature: GTO Explanation + Exploitative Override

After the solver produces the GTO strategy, NeuralGTO should do two things:

**Step 5A — Explain WHY (already partially there)**
- Don't just say "raise 78%". Explain the *strategic logic*:
  - Blockers, balance, range advantage, board texture equity
  - Why this hand specifically (not just the overall range)
  - What principle is being applied (protection, polarity, pot geometry)

**Step 5B — Exploitative Override (NEW)**
- User can describe what they know about the population or specific opponent:
  > "My opponent folds to c-bets too much and never bluff-raises"
  > "This is a soft live 1/2 game where people overcall preflop"
  > "Villain has been very passive postflop"
- The LLM takes the solver's GTO baseline and reasons about how to *deviate*:
  > "GTO says bet 33% of the time here. But against a player who folds too much
  > to bets, you should bet *more* often (closer to 70-80%) as a pure exploit.
  > You're giving up balance, but you don't need balance — villain isn't
  > punishing you for it. Do NOT slowplay your strong hands either; value bet
  > relentlessly."
- This is the bridge between theoretical GTO and practical table decision-making

---

### Why Neither Competitor Does This

| Feature | GTO Wizard | PioSOLVER | **NeuralGTO** |
|---|---|---|---|
| Shows GTO frequencies | ✓ | ✓ | ✓ |
| Explains *why* those frequencies exist | ✗ | ✗ | **✓** |
| Explains principles behind the strategy | ✗ (external blog) | ✗ | **✓** |
| Exploitative deviation suggestions | ✗ | ✗ (nodelock only) | **✓** |
| User describes opponent tendencies in NL | ✗ | ✗ | **✓** |
| Adjusts strategy based on opponent profile | ✗ | Manual only | **✓ Automatic** |

**PioSOLVER has "Opponent Profiling" (nodelock)** — you can manually set a node
to force the opponent to, say, never bluff. It will re-solve with that constraint.
But it requires in-depth technical knowledge of the tree, and still gives you
*zero explanation* of what changed or why. NeuralGTO can wrap that entire
workflow in a single natural language exchange.

---

### Is This Doable? Yes.

The architecture already supports it. Here's what changes:

**Minimal version (weeks):**
- Extend the advisor prompt (`advisor_system.txt`) with explicit instructions to
  explain *why* the suggested action frequency exists — blockers, range balance,
  board texture, equity realization
- Add a `population_notes` optional field to the query input
- Pass that field to the advisor prompt with instructions: "If opponent tendencies
  are provided, reason about exploitative deviations from the GTO baseline"

**Full version (1-2 months):**
- Add a dedicated `ExploitAdvisor` module (separate from `nl_advisor.py`)
- User describes opponent: "folds too much to c-bets, never bluff-raises, passive
  postflop"
- System parses that into `OpponentProfile` (call_freq, bluff_freq, aggression, etc.)
- LLM reasons: "Given this profile, here is the GTO baseline and here is how/when
  to deviate and why"
- Could even suggest *nodelocked* solver runs: "Want me to re-solve this with
  villain's bluffing frequency forced to 0%?"

---

## Where We Are Right Now

### ✅ What's Working
- **Full 5-step pipeline** end-to-end:
  `NL text → Gemini parse → solver input → TexasSolver CFR → strategy extract → Gemini explain`
- **3 analysis modes**: Fast (LLM-only, ~10s) / Default (2% accuracy, ~1-2min) / Pro (0.3% accuracy, ~4-6min)
- **Two interfaces**: Streamlit web UI + interactive CLI
- **Caching**: hash-based, persistent — identical spots answered instantly
- **Sanity checking**: Gemini reviews extreme solver frequencies
- **Graceful fallback**: solver unavailable or preflop → Gemini-only mode
- **6 passing unit tests** (offline, no API key needed)
- **Git + GitHub**: NeuralGTO repo initialized, solver binary excluded

### ⚠️ Known Limitations
| Gap | Impact | Severity |
|---|---|---|
| Windows-only solver binary | Can't deploy to Linux servers / Mac | High |
| No preflop solving | Preflop spots use LLM approximation, not GTO | High |
| 2-player solver only | Multi-way pots fall back to Gemini | Medium |
| 1–6 minute solve time | Not real-time; not suitable for live play decisions | Medium |
| No input validation UI | Vague queries silently produce low-quality output | Medium |
| No range visualization | Strategy is always text; hard to grasp at a glance | Low |
| 3 Gemini calls per pipeline | Token cost + latency compound | Low |

### How to Test Right Now (Terminal, No Browser)
```bash
# Activate venv first
.venv\Scripts\Activate.ps1

# Quick single-shot query (LLM-only, instant)
python -m poker_gpt.main --mode fast --query "I have QQ on BTN vs UTG 4bb raise, 100bb effective, 6-max"

# Interactive REPL (type questions, switch modes mid-session)
python -m poker_gpt.main

# Full solver pipeline (needs solver_bin\ populated)
python -m poker_gpt.main --mode default --query "I have AK on BTN..."

# Run offline unit tests
python -m pytest poker_gpt/tests/ -v

# Debug mode (verbose step output)
python -m poker_gpt.main --debug --mode fast --query "..."
```

---

## Next Steps — Brainstorm

Roughly ordered from "smallest lift → biggest lift". Doesn't have to follow this order.

---

### 🔧 Tier 1 — Quick Wins (days, mostly polish)

**1.1 — Input Validation & Helpful Error Messages**
- Currently: vague user inputs silently produce mediocre Gemini output
- Fix: after parsing, detect missing fields (no hand? no position?) and prompt the user to clarify
- Bonus: add example queries to CLI startup screen

**1.2 — `.env` Setup Check on Startup**
- If `GEMINI_API_KEY` is missing or malformed, fail fast with a clear fix message
- Could also check solver binary presence and print a setup checklist

**1.3 — Better CLI Output Formatting**
- Colorize terminal output (e.g. `rich` library)
- Show a clean strategy table: `Raise 78% | Call 22% | Fold 0%`
- Execution stats: parse time / solve time / cache hit

**1.4 — Logging & History**
- Save each query + advice to a session log (`~/.neuralgto/history.jsonl`)
- `python -m poker_gpt.main --history` shows past queries
- Useful for reviewing your own study sessions

**1.5 — Shortdeck Poker Mode**
- TexasSolver already supports shortdeck (it's a YAML rule file change)
- Just needs a `--variant shortdeck` CLI flag + config toggle
- Probably a few hours of work

---

### 🏗️ Tier 2 — Meaningful Features (1–2 weeks each)

**2.0 — GTO Explanation + Exploitative Override** ⭐ NEW TOP PRIORITY
- See the full write-up in the "Core Differentiator" section above
- **Phase 1 (days):** Extend `advisor_system.txt` to always explain *why* the
  frequencies exist — blockers, range balance, board texture, equity realization
- **Phase 2 (weeks):** Add optional `--opponent` flag to CLI:
  `python -m poker_gpt.main --opponent "folds too much to bets, passive postflop" --query "..."`
- **Phase 3 (1-2 months):** Full `ExploitAdvisor` module with structured
  `OpponentProfile` parsing and nodelocked re-solve suggestions
- This is the feature that neither GTO Wizard nor PioSOLVER has, and it's our
  single biggest differentiator

**2.1 — Preflop Lookup Tables (Replace LLM Fallback)**
- Current preflop advice is Gemini approximation — not GTO
- Options:
  - **A)** Pre-computed GTO preflop charts scraped from public sources and stored as JSON lookup tables
  - **B)** Integrate a preflop solver (OpenFold or TexasSolver with full preflop tree)
  - Option A is low-effort and already meaningfully better than LLM-only
- Impact: The pipeline currently falls back on ~40% of queries (all preflop scenarios)

**2.2 — Range Visualization (Text-Based First)**
- Display a simple ASCII 13x13 hand grid in the terminal showing fold/call/raise frequencies
- Example:
  ```
       A    K    Q    J    T
  A [ R:1.0 R:.9  R:.8  R:.7  R:.5 ]
  K [ R:.9  R:.6  C:.8  ...        ]
  ...
  ```
- Could later upgrade to a Streamlit heatmap

**2.3 — Hand History Import (Single Hand)**
- Parse a `PokerStars` or `GGpoker` hand history format
- Extract the spot from the log and feed it into the pipeline automatically
- Very useful for post-session study — "let me review this hand I just played"

**2.4 — Confidence / Quality Score**
- The pipeline knows whether advice came from solver vs Gemini, and if the solve was accurate
- Surface this clearly as a `[Confidence: High / Medium / Low]` label
- Users should know when to trust the output

**2.5 — Sensitivity / Exploitative Analysis**
- After getting GTO strategy, ask: "What changes if villain folds too much to c-bets?"
- Have Gemini reason about exploitative deviations on top of the GTO baseline
- Bridges GTO theory with real-world exploitative play

---

### 🚀 Tier 3 — Big Projects (weeks to months)

**3.1 — Linux/Mac Support + Cloud Deployment**
- TexasSolver has a Linux build available on their GitHub
- With cross-platform support → deployable on **Streamlit Cloud** (free), **Railway**, or **Render**
- Public URL = shareable link for resume, demo to others, or showing coaches
- This is probably the highest-leverage "portfolio" move right now

**3.2 — REST API Layer**
- Wrap `analyze_hand()` in a FastAPI endpoint
- `POST /analyze` → JSON response with advice, strategy, metadata
- Enables: mobile apps, Discord bot, browser extension, 3rd-party integrations
- Opens the door to eventually charging for API access

**3.3 — Discord Bot**
- Poker players live in Discord servers
- A `/handcheck @QQ BTN vs UTG 4bb` command via Discord.py would get real usage immediately
- Great for virality / organic discovery

**3.4 — Training Mode (Quizzes)**
- Given a spot, hide the answer and ask the user what they'd do
- Compare user answer vs GTO
- Track right/wrong over time → spaced repetition for common spots
- Could be CLI-first, then web

**3.5 — Full Session Hand History Review**
- Import a full PokerStars session file (dozens or hundreds of hands)
- Pipeline identifies the most strategically interesting/costly spots
- Generates a "study report": "You left the most EV on the table with QQ on a KT2 flop"
- This becomes the core value prop for serious players

**3.6 — Swap in a Different LLM**
- Currently hard-wired to Gemini
- Abstract out the LLM calls behind a `LLMProvider` interface
- Support: Gemini (current) / OpenAI GPT-4o / Claude / local (Ollama)
- Opens user flexibility + reduces API vendor risk

**3.7 — Replace Solver with Neural Approximator**
- TexasSolver CFR is slow (1–6 min). What if we trained a neural net on solver outputs?
- "Neural fictitious self-play" or distilled network approximating GTO
- Real-time inference (~100ms)
- This becomes the core research contribution of the project

---

### 🎓 Resume / Showcase Angles

A few ideas specifically for making this more impressive on paper:

- **Write a short technical blog post** — "How I built a neuro-symbolic poker AI" — post to Medium or personal site
- **Add a demo GIF to the README** — terminal or Streamlit demo, makes the repo instantly interesting
- **Deploy publicly** (even read-only demo mode) — a live URL you can put in your resume link
- **Benchmark accuracy** — compare NeuralGTO advice vs known GTO charts on standard spots, publish results
- **Add a paper-style README** — abstract / method / results sections, makes it feel research-grade

---

### Priority Pick (Recommended Starting Point)

**The single most important thing to build next is the "Why" layer + Exploitative Override.**

Phase 1 is literally a prompt edit — a few hours of work. Extend `advisor_system.txt`
to explicitly instruct Gemini to:
1. Explain the strategic *principle* behind the solver frequency (not just state it)
2. If the user mentions opponent tendencies, reason about whether to deviate from GTO and how

This immediately makes NeuralGTO the only tool in the market that gives you a
solver-grounded strategy *and explains the principles behind it*. Nothing else does this.

After that: **Phase 2 (`--opponent` flag)** — another few days, massive UX upgrade.

Runner-up: **3.1 Linux/Mac + Cloud Deploy** for maximum visibility and shareability.

---

*This file is a living brainstorm — update it as ideas evolve.*

