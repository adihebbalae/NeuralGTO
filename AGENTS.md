# AGENTS.md
<!-- Auto-loaded at session start. Keep this file current. -->

## Project
NeuralGTO — neuro-symbolic GTO poker study tool. Python + Streamlit. Dark theme.
Pipeline: NL text → Gemini parse → TexasSolver CFR → GTO strategy extract → Gemini explain.
This is a **study tool**, not a bot. Dual goals: deployable product + publishable research paper.

## Session Startup
Read these files in order before doing any work:
1. `_priv/AGENT-STATE.md` — orientation, key files, open threads, key decisions, hard rules
2. `_dev/AGENT_STATE.md` — DAG wave tracker (what's complete / in-progress / blocked)
3. `_priv/NEXT_STEPS.md` — consult if user asks what to work on next

At session end: append an entry to `_dev/CAPTAINS_LOG.md` (write-only audit trail — do not read during planning).

## Hive Mind — Agent Broadcasting

**Canonical state lives in the private `neuralgto_state` repo: `https://github.com/adihebbalae/neuralgto_state`**
Both local agents and ECE LRC research agents clone this repo separately from the product repo. `_dev/AGENT_STATE.md` is a local working reference only.

**Rules:**
- **Before starting any task:** `cd ~/neuralgto_state && git pull origin main` → update `HIVE_MIND_ACTIVE.md` → `git commit -m "hive: [TaskID] IN PROGRESS" && git push`
- **When you finish:** pull → update status to `✅ COMPLETE` / `⚠️ BLOCKED` / `❌ FAILED` → commit + push
- **When you discover something** another agent needs: write it into the relevant `neuralgto_state` file — never only in a chat response
- Never communicate status only through the user. If you have a finding, write it to `neuralgto_state` so the next agent picks it up cold
- **Parallel tracks:** Product (W5.0) on `main` branch. Research (T4.2) on `research` branch. Use PRODUCT_TRACK.md vs RESEARCH_TRACK.md accordingly.

## Orchestrator System (HMAS)

Five specialized agent modes live in `.github/agents/`. Route work based on intent:

| Intent | Agent File | Use When |
|--------|-----------|----------|
| **Managing** | `.github/agents/MANAGER.agent.md` | Back-and-forth discussion, interpreting output, quick routing, reality-checking ideas |
| **Planning** | `.github/agents/PLANNER.agent.md` | Formal day plan, structured dispatch with execution prompts |
| **Research** | `.github/agents/RESEARCH_ORCHESTRATOR.agent.md` | Wave 4 tasks, benchmarks, eval methodology, paper writing |
| **Product** | `.github/agents/ENGINEER.agent.md` | Wave 1–3 tasks, shipping features, UI, bug fixes |
| **Security** | `.github/agents/SECURITY.agent.md` | Penetration testing (Shannon + VibePenTester), breaking code, generating patches, pre-deployment hardening |

**Workflow:**
- Use MANAGER for lightweight back-and-forth — costs almost nothing, handles 80% of questions
- Use PLANNER when you need a structured day plan with routed execution prompts
- Use ENGINEER or RESEARCH_ORCHESTRATOR in task-focused chats for implementation work
- Use SECURITY for red team testing, MVP hardening, and vulnerability patch generation
- Tasks can be parallelized across chats

## Hard Rules
- **Never commit** `.github/`, `_priv/`, `_dev/`, `_notes/`, `solver_bin/`, `.env`
- Run `git status` before every commit; unstage any of the above immediately if staged
- Never hardcode API keys, model names, or paths — always use `config.*`
- Never let `solver_runner.py` raise on failure — it returns `None`
- Never crash the pipeline — always degrade gracefully to LLM-only mode
- Run `python -m pytest poker_gpt/tests/ -v -k "not test_full_pipeline_with_api"` before committing
- **Always update AGENT_STATE.md HIVE MIND table** when starting or completing any formal task
- **`main` branch = product only** (React UI, FastAPI, W5.0). Never commit research experiments to main.
- **`research` branch = research only** (T4.2 tree pruning, eval scripts, paper experiments). Never merge product UI code into research.

## Compute Resources
- **Local:** Windows laptop + NPU/GPU, Ollama (qwen2.5:7b/14b), TexasSolver Windows binary
- **Remote (free):** UT ECE LRC SSH servers — 32-core Intel Xeon, 384 GB RAM, RHEL 8.10. CPU-only (no GPU confirmed). Requires ECE-LRC account + VPN from off-campus. Good for: long solver runs, multi-core eval jobs. Details in `_dev/AGENT_STATE.md` Compute section.
- **Remote SSH trigger:** If a task will take >1 hour locally AND is CPU-parallelizable, ENGINEER proposes running it on UT ECE. See `ENGINEER.agent.md` for workflow.

## Active Design Tokens
```css
--bg-base: theme('colors.slate.950');
--bg-raised: theme('colors.slate.900');
--bg-overlay: theme('colors.slate.800');
--border: rgba(255,255,255,0.08);
--text-primary: theme('colors.slate.100');
--text-secondary: theme('colors.slate.400');
--signal-positive: theme('colors.emerald.400');   /* EV-positive */
--signal-negative: theme('colors.rose.400');       /* EV-negative */
--signal-neutral: theme('colors.amber.400');       /* frequencies */
```

## Design Boundaries
- **Never use:** Inter, Roboto, Arial, system fonts, arbitrary px values off 4px grid, purple/white schemes, box-shadow elevation, solid `#000` or `#fff` backgrounds
- **Always use:** IBM Plex Mono for data/numbers, IBM Plex Sans for prose, slate-950 base, borders-only depth strategy


# NeuralGTO — Agent Design Memory

Last updated: 2026-02-27

## Established Design Decisions

### Direction
- Personality: Precision & Density (Data & Analysis variant)
- Theme: Dark always
- Foundation: Slate (cool, technical)
- Depth strategy: Borders-only (no box-shadow elevation)

### Spacing
- Base unit: 4px
- Scale in use: 4, 8, 12, 16, 24, 32, 48
- No arbitrary values

### Typography
- Data font: IBM Plex Mono (loaded from Google Fonts)
- Prose font: IBM Plex Sans
- Weight contrast: 200 (labels) / 700 (values)

### Colors
```css
--bg-base: theme('colors.slate.950');
--bg-raised: theme('colors.slate.900');
--bg-overlay: theme('colors.slate.800');
--border: rgba(255,255,255,0.08);
--text-primary: theme('colors.slate.100');
--text-secondary: theme('colors.slate.400');
--signal-positive: theme('colors.emerald.400');
--signal-negative: theme('colors.rose.400');
--signal-neutral: theme('colors.amber.400');
```

### Established Component Patterns
- Button (primary): height 36px, px-4, font-medium, bg-emerald-500, rounded-md
- Card: border border-white/8, p-4, rounded-lg, bg-slate-900
- Data value: font-mono font-bold text-slate-100
- Label: font-sans font-light text-slate-400 text-sm uppercase tracking-wide
- Frequency badge: font-mono text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded

### Motion & Animation
- One orchestrated page load with staggered reveals via `animation-delay`
- Subtle number-tick animations for EV values
- CSS-only preferred; avoid JS animation libraries for simple transitions

### Backgrounds
- Layered CSS gradients or subtle grid patterns
- Never solid `#000` or `#fff`