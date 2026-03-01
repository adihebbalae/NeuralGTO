# Changelog

All notable changes to NeuralGTO are documented here.

## [1.0.0] — 2026-03-01

### MVP Launch — Open-Source Neuro-Symbolic GTO Trainer

**Core Pipeline**
- Complete 5-step neuro-symbolic architecture: parse → solve → extract → advise
- Postflop GTO solving via TexasSolver CFR engine (all board textures, all streets)
- Preflop GTO lookup via pre-solved ranges (GTO Nexus data, 6-max common spots)
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
- Evaluated on PokerBench: 74.5% accuracy on 424 multi-way preflop scenarios

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
- GTO Lookup: 88.5% accuracy on 244 HU preflop scenarios
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
