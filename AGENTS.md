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

## Hard Rules
- **Never commit** `.github/`, `_priv/`, `_dev/`, `_notes/`, `solver_bin/`, `.env`
- Run `git status` before every commit; unstage any of the above immediately if staged
- Never hardcode API keys, model names, or paths — always use `config.*`
- Never let `solver_runner.py` raise on failure — it returns `None`
- Never crash the pipeline — always degrade gracefully to LLM-only mode
- Run `python -m pytest poker_gpt/tests/ -v -k "not test_full_pipeline_with_api"` before committing

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