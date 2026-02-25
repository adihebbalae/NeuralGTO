# Are We Scooped? Competitive Analysis

**Sources:**
- https://github.com/HarperJonesGPT/PokerGPT
- https://arxiv.org/abs/2401.06781

---

## Project 1 — HarperJonesGPT/PokerGPT (GitHub, ~2023)

**What it is:** A real-time automated poker **playing bot** for PokerStars.
- Uses Tesseract OCR + pixel detection to read the screen (cards, pot, dealer button, all actions)
- Feeds the extracted game state into GPT-4 for a decision (fold/check/raise/bet)
- Simulates mouse clicks inside PokerStars to actually execute the decision automatically
- Has a built-in GUI for monitoring + voice audio playback of actions
- 222 GitHub stars, 66 forks, abandoned ~3 years ago

### Pros
- Actually plays live poker hands in real time — zero manual input from user
- Screen-reading approach is clever: works without any API from the poker site
- GUI + voice feedback is a nice UX touch
- Open source, simple to understand architecture

### Cons
- **It's a cheat bot.** Violates PokerStars ToS; gets your account banned. Not educational.
- Purely LLM (GPT-4) for strategy — zero GTO mathematical grounding. GPT-4 plays on vibes.
- Brittle: works only on PokerStars, only 6-player cash tables, only 1920×1080 screen
- No fallback, no accuracy modes, no explanation of _why_ a decision is made
- Abandoned. Author explicitly says "I do not provide support. If you can't figure it out, it's not for you."
- No solver, no range analysis, no concept of Nash equilibrium or exploitability

---

## Project 2 — "PokerGPT: An End-to-End Lightweight Solver for Multi-Player Texas Hold'em via LLM" (Huang et al., arXiv Jan 2024)

**What it is:** An academic paper proposing a **fine-tuned LLM as a standalone poker solver**.
- Collects real hand history text records from actual multi-player games
- Filters records: keeps only actions from high win-rate players
- Applies prompt engineering to clean and format the data
- Fine-tunes a **lightweight LLM using RLHF** on those filtered records
- The fine-tuned LLM itself becomes the "solver" — no CFR, no external binary
- Claims to outperform prior approaches (DeepStack, Libratus baselines) in win rate, model size, training time, and inference speed

### Pros
- **Multi-player support** — the single biggest gap in CFR-based approaches (CFR is 2-player or exponentially expensive)
- Lightweight model → fast inference, potentially real-time
- End-to-end: one model handles everything (no solver subprocess, no output parsing)
- Trained on real human high win-rate data → captures exploitative play naturally
- Academic rigor: reproducible experiments, ablation studies, proper evaluation

### Cons
- **Not GTO.** Trained on human data → learns human tendencies and biases, not Nash equilibrium. A truly GTO opponent would exploit it.
- "Fine-tune a lightweight LLM" is a research project, not a usable tool — no public model weights, no demo, no API
- Requires collecting and curating a large hand history dataset (a huge barrier to reproduction)
- Black-box: tells you what to do but gives zero explanation of _why_
- No natural language interface — it's a research prototype for academic benchmarking
- Handles only preflop scenarios in the evaluation; postflop details are limited

---

## Are We Just Copying?

**Short answer: No.** The overlap is in _name_ only.

| Property | HarperJones/PokerGPT | Huang et al. (arXiv) | **NeuralGTO (us)** |
|---|---|---|---|
| Purpose | Automated cheat bot | Academic benchmark | **Educational advisor** |
| GTO / Nash correctness | ✗ None | ✗ Heuristic (human data) | **✓ CFR solver (guaranteed)** |
| NL user interface | ✗ Fully automated | ✗ Research only | **✓ Type any hand in plain English** |
| Explains reasoning | ✗ No | ✗ No | **✓ Full NL explanation of strategy** |
| Human-in-the-loop | ✗ Bot takes over | ✗ No user interaction | **✓ User asks, system advises** |
| Multi-player | ✓ (6-player) | ✓ (arbitrary) | ✗ (2-player, fallback for 3+) |
| Speed | ✓ Real-time | ✓ Fast inference | ⚠ 10s–6min depending on mode |
| Accuracy basis | GPT vibes | Human heuristics | **Mathematical CFR convergence** |
| Transparency | ✗ Black box | ✗ Black box | **✓ Shows frequencies, source, confidence** |
| Deployable & usable | ✓ (barely) | ✗ No | **✓ Today, CLI + web UI** |

### What Makes NeuralGTO Genuinely Different

1. **GTO correctness is the core value prop.** Neither competitor touches a CFR solver. We do. When NeuralGTO gives you a strategy, it's backed by the same mathematics as commercial tools like PioSOLVER that sell for $500+.

2. **It's an advisor, not a bot.** We're building something legal (offline study tool), sustainable (not ToS-violating), and educational (explains _why_). That's a completely different product category.

3. **Natural language both ways.** You describe a hand in plain English → you get advice in plain English. No OCR, no screen scraping, no rigid input format. The pipeline is the contribution.

4. **Transparency.** We show you the exact solver frequencies (`Raise 78% | Call 22%`), the source (`solver` vs `llm_only`), and sanity check flags. Users learn, not just follow orders.

5. **Graceful degradation.** Three modes with explicit accuracy/time tradeoffs. Never crashes. GTO purity when available, reasonable approximation when not.

---

## What We Should Steal (Good Ideas They Have)

### From HarperJones
- **OCR screen reader** — Instead of the user typing "I have QQ, UTG raised to 4bb...", automatically read it from the PokerStars/GGPoker window. This would be an incredible UX improvement. Could be an optional `--screen` mode.

### From Huang et al.
- **Fine-tune on high-win-rate hand histories** — Could use this technique to improve the NL parser (Step 1). Instead of prompting Gemini cold, fine-tune a small model on labeled parsing examples. Makes range estimation more accurate.
- **Prompt engineering pipeline for hand records** — Their data filtering strategy (only keep high win-rate player actions) is directly applicable to building a preflop lookup table or a training set for the LLM fallback.
- **Multi-player framing** — The RLHF approach handles N-player naturally. We could use it as the multi-way fallback instead of raw Gemini — a fine-tuned model on 3-way/4-way spots would be far more accurate than prompting Gemini with no training signal.
- **Academic framing for resume/paper** — They wrote a paper on this. We could too. The neuro-symbolic hybrid (CFR + LLM in one pipeline) is a genuinely novel framing that hasn't been published. Write it up when more mature.

---

## Bottom Line

We're not copying — we've independently converged on the name (unfortunate) but built something structurally different. The real competition is **commercial tools** like PioSOLVER, GTO Wizard, and Solver+, which charge real money for solver access without any natural language layer.

**Our unique angle:** CFR-grounded + natural language in/out + educational + free/open source. None of the three above (HarperJones, Huang et al., commercial tools) hits all four simultaneously.

The risk isn't being scooped. The risk is that GTO Wizard already has a massive moat. Design around it: position NeuralGTO as the **open-source, explainable, study-focused alternative** — not a competitor to live real-time advisors.
