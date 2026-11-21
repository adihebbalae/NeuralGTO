# Changelog

All notable changes to NeuralGTO are documented here.

## [Unreleased] — 2026-11-20

### Documentation and license hygiene (no code behavior change)

- **Removed `poker_gpt/preflop_charts/jonathan_little_gto.json` from the tree.** It was a
  conversion of third-party commercial preflop charts (Jonathan Little) and should not have
  been committed under MIT. No code loaded it: `preflop_lookup.py` reads TexasSolver's
  bundled `qb_ranges` files, and `tests/test_preflop_charts.py` reads an untracked local copy
  under `_dev/` and skips when that copy is absent. The file is still in git history from
  commit 2089ee3 (v1.0.0) onward; history was not rewritten.
- **Added `NOTICE` and a license notice in `vendor/README.md`:** the
  `vendor/texassolver-neuralgto-opt.patch` file is a derivative of AGPL-3.0 TexasSolver and is
  licensed AGPL-3.0, not MIT.
- **Fixed the PokerBench citation.** The README linked arXiv:2401.06781, which is Huang et
  al.'s PokerGPT paper. PokerBench is Zhuang et al., arXiv:2501.08328.
- **Stated what the PokerBench numbers measure:** preflop only, action-category match; the
  lookup's 88.5% covers 244 of 1,000 scenarios (24.4%).
- **Added the multi-way baseline:** Gemini direct scored 77.4% on the same 424 multi-way
  scenarios where the pairwise pipeline scored 74.5%.
- **Corrected the preflop data source:** docs said "GTO Nexus data"; the code reads the
  `qb_ranges` files bundled with the TexasSolver v0.2.0 release.
- **Qualified the 2.27x solver speedup:** measured on local Windows; the hosted Oracle
  backend ran a stock TexasSolver build.


## [1.1.0] — 2026-08-24

### Final Release — Project Archived

NeuralGTO is sunset as of August 2026. This entry captures everything that
shipped after the 1.0.0 MVP. No further releases are planned.

**Full-Stack Rewrite (Wave 5.0)**
- React 19 + TypeScript + Vite SPA (`neuralgto-web/`) replacing Streamlit as the primary UI
- FastAPI backend (`backend/`) wrapping the existing `analyze_hand()` pipeline — no pipeline logic duplicated
- `POST /api/analyze` — NL hand description → structured advice, rate limited, async execution
- `POST /api/reanalyze-street` — interactive turn/river card picker re-runs the solver on selection
- `GET /api/health` — liveness plus a live `solver_available` flag wired to `is_solver_available()`
- Structured advice output: top 3 EV plays, per-street review, `StructuredAdviceResponse` schema
- SVG poker table visualization, card picker, error boundary, typed API client
- Shared request/response contract between Pydantic schemas and TypeScript types

**Deployment (all free tier, $0/month)**
- Frontend on Cloudflare Pages (`neuralgto.pages.dev`)
- Full-solver backend on Oracle Cloud Always Free (Ampere A1, ARM64)
- LLM-only fallback backend on Google Cloud Run (instant, no solver)
- HTTPS to the Oracle VM via a Cloudflare Worker proxy
- Deploy artifacts: `setup_oracle.sh`, systemd unit, nginx config, cloudflared tunnel config, Dockerfile
- Runbooks: `docs/DEPLOYMENT.md`, `docs/CLOUD_RUN_DEPLOYMENT.md`

**Native ARM64 Solver**
- TexasSolver built from source on Ampere (Qt6) — no upstream ARM64 release exists
- Fixed compairer binary cache fallback bug that silently disabled the solver
- Fixed systemd namespace hardening that blocked solver subprocess execution

**Solver Performance Fork (~2.3x)**
- Performance fork of TexasSolver's `console` branch; reproducible from `vendor/texassolver-neuralgto-opt.patch` + build scripts (fork not vendored — upstream is AGPL-3)
- 67.5s → 29.8s at 8 threads on the benchmark flop spot (2.27x vs stock v0.2.0); 22.3s at 16 threads. Measured on local Windows only: the hosted Oracle backend ran a stock build and never got this speedup
- Output agrees with stock within 0.03% mean per-action frequency
- Changes: cached strategy vectors, lock-free precomputed river ranges (SoA layout), raw-pointer CFR recursion, OpenMP scheduling fix, copy elimination, `-O3 -march=native` + LTO, mimalloc global allocator
- Also fixed upstream's `system_clock` progress timing jumping on NTP resync

**Security Hardening**
- Rate limiter proxy-header fix (real client IP behind Cloudflare)
- CORS origin allowlist; CSP tightened on Cloudflare Pages `_headers`
- Pre-push validation hook (pytest + secret scan), Windows git-bash compatible
- Log sanitization, pinned Dockerfile base image, documented Cloud Run IAM setup

**Configuration**
- Default mode eased to 50 iterations / 5% exploitable / 60s timeout for responsive web use

**Research (paused, not shipped)**
- T4.1 pairwise HU decomposition — complete, 74.5% on 424 multi-way PokerBench preflop scenarios; Gemini direct scored 77.4% on the same 424 (T4.3)
- T4.3 method comparison eval — complete, results archived
- T4.2 LLM-guided tree pruning — partial (2/5 spots, 3 known bugs); T4.2c never started
- Paper (CoG / AAAI Demo target) — not written

**Testing**
- 493 tests collected across `poker_gpt/tests/` and `backend/tests/`
- Vitest suite for the React frontend

### Sunset Notes
- The Cloudflare Worker fronting the Oracle backend lives only in the Cloudflare dashboard — no source in this repo
- Hosted demo may lapse at any time; local usage needs only a free Gemini API key
- Post-sunset roadmap and unfinished research directions were written up outside this repo

---

## [1.0.0] — 2026-03-01

### MVP Launch — Open-Source Neuro-Symbolic GTO Trainer

**Core Pipeline**
- Complete 5-step neuro-symbolic architecture: parse → solve → extract → advise
- Postflop GTO solving via TexasSolver CFR engine (all board textures, all streets)
- Preflop GTO lookup via pre-solved ranges (the `qb_ranges` files bundled with the TexasSolver v0.2.0 release, 6-max common spots; originally mislabeled "GTO Nexus data", corrected 2026-11-20)
- Graceful fallback: solver unavailable → LLM-only mode (never crashes)
- Three analysis modes: fast (LLM-only ~10s), default (2% ~1-2min), pro (0.3% ~4-6min)

**GTO Explanation Layer**
- Explains *why* each action is correct (blockers, range balance, board texture, equity realization)
- Trust badges on every response (solver-verified vs LLM approximation)
- Table-ready heuristics — one-line "Table Rule" for live play
- Sanity checker — LLM reviews extreme solver frequencies

**Exploitative Play**
- Opponent tendency override — describe villain, get adjusted strategy
- Live game prep mode — pool-level exploitative adjustments
- Always shows GTO baseline first, then deviation

**Multi-way Support**
- Pairwise HU decomposition for 3+ player spots
- LLM synthesis with multi-way theory (MDF compression, sandwich effect)
- Evaluated on PokerBench: 74.5% accuracy on 424 multi-way preflop scenarios (action-category match; Gemini direct later scored 77.4% on the same 424)

**Study Tools**
- Quiz mode with scoring engine (48 tests)
- Spot frequency data and study prioritization
- Hand history import (PokerStars, GGPoker, Winamax)
- Session history and logging
- Beginner/Advanced output modes

**CLI Features**
- Interactive REPL with conversational gap-filling
- Range visualization (13×13 ASCII grid via Rich)
- Rich-formatted output (colors, tables)

**Web Interface**
- Streamlit web UI with progress tracking
- Real-time solver status updates
- Account system with free-tier gating

**Security**
- Input sanitization (14 injection pattern regexes)
- Rate limiting (per-session, global, per-IP)
- Brute-force login protection (5 attempts / 15-min lockout)
- Email validation (format + disposable blocklist + DNS MX)
- Daily budget tracking (API cost control)
- Solver binary path validation (prevents arbitrary execution)

**Testing**
- 425+ offline unit tests (no API key or solver binary needed)
- Covers: pipeline, preflop lookup, hand history, multiway, quiz, security, evaluation

**Evaluation**
- PokerBench framework integration
- GTO Lookup: 88.5% accuracy on 244 HU preflop scenarios (the 244 of 1,000 the lookup could match, 24.4% coverage)
- Gemini Direct: 86.5% baseline
- Pairwise LLM: 74.5% on 424 multi-way scenarios

### Known Limitations
- TexasSolver is heads-up postflop only (multi-way uses pairwise decomposition)
- Windows solver binary only (Linux binary available from TexasSolver releases)
- ~1-3 min per postflop spot (not real-time)
- SHA-256 password hashing (bcrypt upgrade planned for Phase 2)

### Dependencies
- Python 3.10+
- Google Gemini API key (free tier works)
- TexasSolver v0.2.0 binary (optional — LLM-only mode works without it)
