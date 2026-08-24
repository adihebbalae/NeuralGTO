# NeuralGTO — Open-Source GTO Poker Trainer

> ## 🗄️ Archived — August 2026
>
> **This project is sunset and no longer under active development.** The code,
> docs, and evaluation results below describe the final shipped state and are
> preserved for reference. Issues and PRs are not being monitored.
>
> The hosted demo still runs on free-tier infrastructure and may disappear
> without notice — see [Deployment Status](#deployment-status). Everything here
> works locally with a free Gemini API key; no hosted service is required.

**Neuro-symbolic poker study tool** combining LLM understanding with solver-level math.

Describe a hand in plain English — get mathematically optimal strategy with human-readable explanations of *why* each action is correct.

```
"I have QQ on the button, villain 3bets from the blinds, 100bb deep"
  → GTO strategy: 4-bet 62%, Call 38%
  → Explanation: blockers, range balance, SPR considerations
  → Optional: exploitative adjustments for specific opponents
```

> **Study tool, not a bot.** Built for post-session review and GTO learning.

---

## What Makes This Different

| Tool | Strategy | Explanation | Natural Language |
|------|:--------:|:-----------:|:----------------:|
| PioSOLVER / GTO Wizard | Exact | None | None |
| ChatGPT / Claude | Approximate | Plausible but wrong | Yes |
| **NeuralGTO** | **Exact (solver)** | **Correct (grounded)** | **Yes** |

- **Solvers** give you perfect math but zero understanding — just frequency tables
- **LLMs** understand language but hallucinate frequencies and invent reasoning
- **NeuralGTO** uses the solver for math and the LLM for explanation, grounding every claim in the actual solution

---

## Quick Start

```bash
# Clone & install
git clone https://github.com/adihebbalae/NeuralGTO.git
cd NeuralGTO
python -m venv .venv && .venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt

# Configure (get a free key at https://aistudio.google.com/apikey)
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=your-key-here

# Run
streamlit run poker_gpt/web_app.py        # Web UI at localhost:8501
python -m poker_gpt.main                   # Interactive CLI
python -m poker_gpt.main --mode pro --query "I have QQ on the BTN..."
```

### Web App (React + FastAPI)

The production stack that shipped in Wave 5 — a React SPA talking to a FastAPI
service that wraps the same `analyze_hand()` pipeline.

```bash
# Terminal 1 — API (http://localhost:8000, docs at /docs)
cd backend && pip install -r requirements.oracle.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (http://localhost:5173, proxies /api → :8000)
cd neuralgto-web && npm install && npm run dev
```

| Endpoint | Purpose |
|---|---|
| `POST /api/analyze` | Full pipeline — NL hand description → structured advice |
| `POST /api/reanalyze-street` | Re-solve after picking a turn/river card |
| `GET /api/health` | Liveness + `solver_available` flag |

The Streamlit UI (`poker_gpt/web_app.py`) still works and is the fastest way to
poke at the pipeline locally, but the React app is what was deployed.

### Analysis Modes

| Mode | Solver | Accuracy | Time | Use case |
|---:|:---:|:---:|:---:|---|
| `fast` | No | — | ~10s | Quick LLM-only approximation |
| `default` | Yes | 2% | ~1-2 min | Good GTO approximation |
| `pro` | Yes | 0.3% | ~4-6 min | Precise GTO solution |

---

## Features

### Core Pipeline
- **5-step neuro-symbolic architecture**: parse → solve → extract → explain
- **Postflop GTO solving** via TexasSolver CFR (all board textures, all streets)
- **Preflop GTO lookup** via pre-solved ranges (6-max, common spots)
- **Graceful fallback**: solver unavailable → LLM-only mode, always returns advice

### GTO Explanation Layer
- **Why, not just what** — explains blockers, range balance, board texture, equity realization
- **Trust badges** — every response shows whether it came from solver or LLM
- **Table-ready heuristics** — bold one-line "Table Rule" for live play
- **Sanity checker** — LLM reviews extreme solver frequencies for edge cases

### Exploitative Play
- **Opponent override** — describe villain tendencies, get adjusted strategy
- **Live game prep** — describe opponent pool, get session-wide adjustments
- **GTO baseline + deviation** — always shows pure GTO first, then how to exploit

### Study Tools
- **Quiz mode** — test yourself on common spots with scoring
- **Spot frequency data** — shows how often you'll encounter each scenario
- **Hand history import** — paste PokerStars/GGPoker/Winamax hand histories
- **Session history** — review past analyses

### Multi-way Hands
- **Pairwise HU decomposition** — breaks 3+ player spots into heads-up pairs
- **LLM synthesis** — combines pairwise results with multi-way theory (MDF compression, sandwich effect)
- Evaluated on PokerBench: 74.5% accuracy on 424 multi-way preflop scenarios

---

## Architecture

```
Plain English ──→ Gemini Parse ──→ TexasSolver CFR ──→ Strategy Extract ──→ Gemini Explain
                  (ScenarioData)   (game tree solve)   (StrategyResult)     (NL advice)
```

| Step | Module | What it does |
|---:|---|---|
| 1 | `nl_parser.py` | NL → `ScenarioData` via Gemini |
| 2 | `solver_input.py` | `ScenarioData` → TexasSolver command file |
| 3 | `solver_runner.py` | Subprocess executor → `output_result.json` |
| 4 | `strategy_extractor.py` | JSON tree → `StrategyResult` for hero's hand |
| 5 | `nl_advisor.py` | `StrategyResult` → coaching advice via Gemini |

Preflop scenarios skip the solver (postflop-only) and use pre-solved GTO lookup tables or LLM fallback. The pipeline never crashes — every failure path degrades gracefully to LLM-only mode with a warning badge.

See [POKERGPT_ARCHITECTURE.md](docs/POKERGPT_ARCHITECTURE.md) for full details.

---

## Solver Setup

TexasSolver is optional — the system works without it (LLM-only mode).

1. Download from [TexasSolver Releases](https://github.com/bupticybee/TexasSolver/releases) (v0.2.0)
2. Extract into `solver_bin/TexasSolver-v0.2.0-Windows/`
3. The paths auto-resolve from the project root — no manual config needed

> **Note:** TexasSolver is heads-up postflop only. Preflop and 3+ player spots use pre-solved lookup + LLM.

### Optimized build (optional, ~2.3x faster)

The production backend ran a performance fork of TexasSolver's `console` branch.
The fork itself is not vendored here (upstream is AGPL-3; this repo is MIT), but
everything needed to rebuild it is in [`vendor/`](vendor/README.md):

| File | Purpose |
|---|---|
| `vendor/texassolver-neuralgto-opt.patch` | Full diff vs upstream `console` |
| `vendor/build_solver.sh` | Windows build (MSYS2 UCRT64 g++) |
| `vendor/build_solver_linux.sh` | Linux / Oracle Ampere ARM64 build |

Measured on the benchmark flop spot: **67.5s → 29.8s at 8 threads** (2.27x vs the
stock v0.2.0 binary), 22.3s at 16 threads, with per-action frequencies agreeing
with stock to within 0.03% mean. The wins come from caching the strategy vector,
a lock-free river-range cache, raw-pointer CFR recursion, OpenMP tuning, and
mimalloc. See `vendor/README.md` for the full write-up.

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
├── preflop_lookup.py        # Pre-solved GTO preflop charts
├── multiway.py              # Multi-way pairwise HU decomposition
├── range_utils.py           # Range math utilities + default GTO ranges
├── range_display.py         # 13×13 hand grid visualization (ASCII + Rich)
├── quiz.py                  # Quiz mode scoring engine
├── spot_frequency.py        # Spot frequency data + study prioritization
├── hand_history.py          # PokerStars/Winamax/GGPoker HH parser
├── cache.py                 # Hash-based persistent solver cache
├── auth.py                  # Lightweight auth + free-tier gating
├── security.py              # Rate limiting, input sanitization, abuse detection
├── validation.py            # Input validation utilities
│
├── prompts/                 # System prompts (advisor, parser, multiway)
├── evaluation/              # PokerBench eval framework
├── preflop_charts/          # Pre-solved GTO data (JSON)
├── tests/                   # 425+ offline tests (pytest)
├── _cache/                  # Cached solver outputs (auto-created)
└── _work/                   # Runtime solver I/O (auto-created)

backend/                     # FastAPI service (wraps poker_gpt, deployed to Oracle)
├── app/main.py              # App factory, CORS, /api/health
├── app/api/analyze.py       # POST /api/analyze, POST /api/reanalyze-street
├── app/models/schemas.py    # Pydantic request/response contract
├── app/services/            # Structured advice formatter (top-3 EV plays)
├── deploy/                  # systemd unit, nginx, cloudflared config, setup_oracle.sh
└── tests/                   # Endpoint tests

neuralgto-web/               # React 19 + TypeScript + Vite SPA (deployed to CF Pages)
├── src/pages/Home.tsx       # Main analysis view
├── src/components/          # PokerTable (SVG), CardPicker, AdviceDisplay, TopPlayCard
├── src/api/client.ts        # Typed fetch client
└── public/_headers          # Cloudflare Pages security headers + CSP

vendor/                      # Optimized TexasSolver fork — patch + build scripts only
```

> `frontend/` holds only the original shared `types/api.ts` contract stub — the
> live frontend is `neuralgto-web/`.

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
✅ Powered by TexasSolver CFR engine

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

# Integration test (needs GEMINI_API_KEY in .env)
python -m pytest poker_gpt/tests/ -v -k "test_full_pipeline_with_api"
```

**493 tests** collected across `poker_gpt/tests/` and `backend/tests/` — pipeline
logic, preflop lookup, hand history parsing, multi-way decomposition, quiz
scoring, security hardening, evaluation framework, and the FastAPI endpoints.
The frontend adds a Vitest suite (`cd neuralgto-web && npm test`).

---

## Configuration

All via environment variables (`.env` file). See `.env.example` for the full template.

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key ([get one free](https://aistudio.google.com/apikey)) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `SOLVER_BINARY_PATH` | *(auto-detected)* | Path to `console_solver.exe` |
| `SOLVER_RESOURCES_PATH` | *(auto-detected)* | Path to solver `resources/` dir |
| `SOLVER_THREAD_NUM` | `4` | Solver thread parallelism |
| `SOLVER_TIMEOUT` | `300` | Solver timeout in seconds |
| `USE_SOLVER` | `true` | Enable/disable solver |
| `POKERGPT_DEBUG` | `false` | Verbose debug logging |
| `LLM_PROVIDER` | `gemini` | `gemini` or `local` (Ollama) |

---

## Known Limitations

- **Heads-up postflop only** — TexasSolver is a 2-player solver. Multi-way spots use pairwise decomposition + LLM synthesis.
- **Solver binary is per-platform** — upstream ships a Windows `console_solver.exe`; the deployed Linux/ARM64 build was compiled from source (see `vendor/`).
- **Preflop** — Solver handles postflop only. Preflop uses pre-solved lookup tables (GTO Nexus data) + Gemini fallback.
- **~30s-3 min per postflop spot** — not real-time. Designed for study, not live play.
- **No exploitability measurement** — strategy quality is compared by L1 distance to a full-tree solve, not NashConv, so pruning claims are not falsifiable as-is.
- **Combo weighting** — `range_utils` / `strategy_extractor` treat all 169 hand classes equally rather than weighting by 4/12/6 combos.

---

## Deployment Status

Last verified March 2026. Everything ran on free tiers; **treat these as
best-effort and expect them to lapse** now that the project is archived.

| Component | Where | Status at sunset |
|---|---|---|
| Frontend | Cloudflare Pages — `neuralgto.pages.dev` | Live, builds from `neuralgto-web/` |
| Backend (full solver) | Oracle Cloud Always Free, Ampere A1 ARM64 | Live at `:8000`, native TexasSolver build |
| Backend (LLM-only fallback) | Google Cloud Run | Live, instant, no solver |
| HTTPS for backend | Cloudflare Worker proxy → Oracle VM | Live |
| Database | Supabase free tier | Provisioned; pauses after 7 idle days |
| Auth | Clerk free tier | Provisioned, not wired into the React app |

Run cost was **$0/month**. Deployment runbooks: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
(Oracle + Cloudflare) and [`docs/CLOUD_RUN_DEPLOYMENT.md`](docs/CLOUD_RUN_DEPLOYMENT.md).

> **Not in this repo:** the Cloudflare Worker that fronts the Oracle backend over
> HTTPS exists only in the Cloudflare dashboard — there is no `wrangler.toml` or
> worker source here. If the Worker is deleted, the deployed frontend loses its
> backend and the runbooks won't reproduce it.

---

## Research

NeuralGTO is also a research project exploring neuro-symbolic approaches to poker strategy. Evaluated on the [PokerBench](https://arxiv.org/abs/2401.06781) benchmark:

| Mode | Scenarios | Accuracy | 95% CI |
|------|-----------|----------|--------|
| GTO Lookup (HU) | 244 | 88.5% | ±4.0pp |
| Gemini Direct (HU) | 244 | 86.5% | ±4.3pp |
| Pairwise LLM (Multi-way) | 424 | 74.5% | ±4.1pp |

Target venues: AAAI Demo Track, CoG, AAMAS.

---

## License

[MIT](LICENSE)

---

## Dependencies

- Python 3.10+
- [google-genai](https://pypi.org/project/google-genai/) — Gemini API client
- [python-dotenv](https://pypi.org/project/python-dotenv/) — env var management
- [Streamlit](https://streamlit.io/) — web UI
- [Rich](https://rich.readthedocs.io/) — CLI formatting
- [TexasSolver](https://github.com/bupticybee/TexasSolver) — *(optional)* CFR solver binary

**Web app:** FastAPI + Uvicorn (backend), React 19 + TypeScript + Vite + Tailwind
(frontend). See `backend/pyproject.toml` and `neuralgto-web/package.json`.
