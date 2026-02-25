# NeuralGTO — Next Steps Brainstorm
**Last updated:** February 25, 2026

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

If you had to pick one thing to do next:

> **2.1 Preflop Lookup Tables** — it's the biggest gap in current pipeline quality,
> affects ~40% of queries, and is 1-2 weeks of work. Immediately makes the tool
> more trustworthy and defensible on a resume.

Runner-up: **3.1 Linux/Mac + Cloud Deploy** for maximum visibility.

---

*This file is a living brainstorm — update it as ideas evolve.*
