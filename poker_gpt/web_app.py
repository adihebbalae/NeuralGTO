"""
web_app.py — PokerGPT Streamlit Web Interface.

A web UI for the PokerGPT pipeline with three analysis modes:
  - Fast:    LLM-only (~10s)
  - Default: Solver with relaxed accuracy (~1-2 min)
  - Pro:     Solver with high accuracy (~4-6 min)

Run with:
    streamlit run poker_gpt/web_app.py

Created: 2026-02-06
"""

import sys
from pathlib import Path

# Ensure project root is importable (when running via `streamlit run`)
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import time
import re
import streamlit as st

from poker_gpt.main import analyze_hand, get_source_badge
from poker_gpt.solver_runner import is_solver_available
from poker_gpt.cache import get_cache_stats, clear_cache
from poker_gpt.hand_history import parse_hand_history, hand_to_query, hands_summary
from poker_gpt import config
from poker_gpt.security import (
    check_rate_limit,
    check_global_rate_limit,
    check_cooldown,
    sanitize_input,
    check_daily_budget,
    detect_abuse,
    record_daily_usage,
    MAX_REQUESTS_PER_SESSION,
)
from poker_gpt.auth import (
    register,
    login,
    check_free_tier,
    record_user_usage,
    check_user_daily_limit,
    get_user_stats,
    FREE_USES_PER_SESSION,
)


# ──────────────────────────────────────────────
# Estimated times per mode (seconds)
# ──────────────────────────────────────────────
_MODE_EST_SECONDS: dict[str, tuple[int, int]] = {
    "fast": (5, 10),
    "default": (60, 120),
    "pro": (240, 360),
}

# Progress mapping: step → (progress_start, progress_end)
_STEP_PROGRESS: dict[str, tuple[float, float]] = {
    "Step 1": (0.0, 0.20),
    "Preflop": (0.20, 0.30),
    "validation": (0.20, 0.30),
    "Step 2": (0.30, 0.40),
    "Step 3": (0.40, 0.80),
    "Step 4": (0.80, 0.90),
    "Step 5": (0.90, 1.0),
    "Generating GTO": (0.20, 0.95),   # LLM-only fast mode
    "Generating advice": (0.20, 0.95),  # preflop lookup advice
    "Sanity": (0.85, 0.90),
    "Cache hit": (0.40, 0.80),
}


def _detect_step(msg: str) -> str | None:
    """Extract the current pipeline step key from a status message.

    Args:
        msg: Status message emitted by analyze_hand's on_status callback.

    Returns:
        A key from _STEP_PROGRESS, or None if no step is detected.
    """
    # Check for explicit step numbers first
    m = re.search(r"Step (\d)", msg)
    if m:
        return f"Step {m.group(1)}"
    lower = msg.lower()
    for key in ("preflop", "validation", "generating gto",
                "generating advice", "sanity", "cache hit"):
        if key in lower:
            return key.title() if key[0].isupper() else key.capitalize()
    return None


# ──────────────────────────────────────────────
# Page Configuration
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# Session ID for rate limiting
# ──────────────────────────────────────────────
if "session_id" not in st.session_state:
    import uuid
    st.session_state["session_id"] = str(uuid.uuid4())
    st.session_state["request_count"] = 0
    st.session_state["free_uses"] = 0  # analyses done anonymously this session
    st.session_state["authenticated"] = False
    st.session_state["user_email"] = None

st.set_page_config(
    page_title="PokerGPT",
    page_icon="♠️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container {max-width: 960px; padding-top: 2rem;}
    div[data-testid="stMetricValue"] {font-size: 1.4rem;}
    .stProgress > div > div {height: 24px; border-radius: 6px;}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Sidebar — Settings & Info
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    solver_ok = is_solver_available()
    st.markdown(f"**Solver:** {'✅ Available' if solver_ok else '❌ Not found'}")
    st.markdown(f"**Model:** `{config.GEMINI_MODEL}`")

    cache_stats = get_cache_stats()
    st.markdown(f"**Cache:** {cache_stats['entries']} entries ({cache_stats['size_mb']} MB)")

    if st.button("🗑️ Clear Cache"):
        cleared = clear_cache()
        st.success(f"Cleared {cleared} cached entries.")
        st.rerun()

    st.divider()
    st.markdown("### 📊 Usage")
    _req_count = st.session_state.get("request_count", 0)
    st.markdown(f"**Session requests:** {_req_count} / {MAX_REQUESTS_PER_SESSION}")
    _within, _daily_remaining = check_daily_budget()
    st.markdown(f"**Daily remaining:** {_daily_remaining}")

    # ── Account section ──
    st.divider()
    st.markdown("### 🔐 Account")
    if st.session_state.get("authenticated"):
        _email = st.session_state["user_email"]
        st.markdown(f"Signed in as **{_email}**")
        _ustats = get_user_stats(_email)
        st.caption(
            f"Today: {_ustats['today_queries']} queries · "
            f"Total: {_ustats['total_queries']} · "
            f"Since {_ustats['member_since']}"
        )
        if st.button("Sign out"):
            st.session_state["authenticated"] = False
            st.session_state["user_email"] = None
            st.rerun()
    else:
        _free_left = max(FREE_USES_PER_SESSION - st.session_state.get("free_uses", 0), 0)
        st.markdown(f"**Free uses left:** {_free_left}")
        st.caption("Sign in for unlimited daily access.")
        _auth_tab = st.radio("", ["Sign in", "Register"], horizontal=True, label_visibility="collapsed")
        _auth_email = st.text_input("Email", key="auth_email")
        _auth_pass = st.text_input("Password", type="password", key="auth_pass")
        if _auth_tab == "Sign in":
            if st.button("Sign in", use_container_width=True, type="primary"):
                ok, msg = login(_auth_email, _auth_pass)
                if ok:
                    st.session_state["authenticated"] = True
                    st.session_state["user_email"] = _auth_email.strip().lower()
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            if st.button("Create account", use_container_width=True, type="primary"):
                ok, msg = register(_auth_email, _auth_pass)
                if ok:
                    st.session_state["authenticated"] = True
                    st.session_state["user_email"] = _auth_email.strip().lower()
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()
    st.markdown("""
### Mode Details

**⚡ Fast** — LLM-only approximation (~10s)
Best for quick reads and preflop spots.

**🎯 Default** — ~98% accuracy (~1-2 min)
Good balance of speed vs precision.

**🏆 Pro** — ~99.7% accuracy (~4-6 min)
Maximum precision.
    """)


# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.title("♠️ PokerGPT")
st.caption("Neuro-Symbolic Poker Advisor — Powered by TexasSolver + Google Gemini")


# ──────────────────────────────────────────────
# Example queries (quick-start)
# ──────────────────────────────────────────────
EXAMPLES = [
    "I have QQ on the button, flop is Ts 9d 4h, villain checks. Pot is 20bb, stacks are 90bb.",
    "I have AKs in the CO, BTN 3bets to 9bb. 100bb effective. What do I do?",
    "I hold 87s on the BB, SB opens to 3bb. Flop is 6h 5d 2c, SB bets 2bb into 6bb pot.",
]

with st.expander("💡 Example hands (click to try)"):
    for ex in EXAMPLES:
        if st.button(ex, key=f"ex_{hash(ex)}", use_container_width=True):
            st.session_state["query"] = ex


# ──────────────────────────────────────────────
# Hand History Import
# ──────────────────────────────────────────────
with st.expander("📂 Import Hand History"):
    hh_file = st.file_uploader(
        "Upload a hand history file (.txt)",
        type=["txt", "log", "csv"],
        key="hh_upload",
    )
    hh_hero = st.text_input(
        "Hero name (leave blank to auto-detect):",
        value="",
        key="hh_hero",
    )
    if hh_file is not None:
        try:
            hh_text = hh_file.read().decode("utf-8", errors="replace")
            hh_hands = parse_hand_history(hh_text, hero_name=hh_hero)
            if not hh_hands:
                st.warning("No parseable hands found in file.")
            else:
                summaries = hands_summary(hh_hands)
                chosen = st.selectbox(
                    f"Select a hand ({len(hh_hands)} found):",
                    options=list(range(len(summaries))),
                    format_func=lambda i: summaries[i],
                    key="hh_select",
                )
                if st.button("Use this hand", key="hh_use"):
                    st.session_state["query"] = hand_to_query(hh_hands[chosen])
                    st.rerun()
        except Exception as e:
            st.error(f"Error parsing hand history: {e}")


# ──────────────────────────────────────────────
# Input Section
# ──────────────────────────────────────────────
query = st.text_area(
    "🃏 Describe your poker hand:",
    value=st.session_state.get("query", ""),
    placeholder="Example: I have QQ on the button, the flop is Ts 9d 4h, "
                "villain checks to me. Pot is 20bb, stacks are 90bb.",
    height=120,
)

# Mode selection — three columns with buttons
st.markdown("**Choose analysis mode:**")
col1, col2, col3 = st.columns(3)

opponent_notes = st.text_input(
    "🎭 Villain tendencies (optional — for exploitative advice):",
    value=st.session_state.get("opponent_notes", ""),
    placeholder=(
        "e.g. 'calling station, never folds' · 'aggro, raises every street' · "
        "'nit, folds too much to bets'"
    ),
    help=(
        "Describe what you know about this villain. NeuralGTO will use GTO as the "
        "baseline and reason about whether to deviate based on these tendencies. "
        "Leave blank for pure GTO advice."
    ),
)
if opponent_notes != st.session_state.get("opponent_notes", ""):
    st.session_state["opponent_notes"] = opponent_notes

pool_notes = st.text_input(
    "🎰 Pool tendencies — Live Game Prep (optional):",
    value=st.session_state.get("pool_notes", ""),
    placeholder=(
        "e.g. 'live 1/2, pool underbluffs, rarely value bets thin, "
        "overcalls preflop, fit-or-fold postflop'"
    ),
    help=(
        "Describe the overall pool tendencies at your game (not a specific villain). "
        "NeuralGTO will generate session-wide exploitative adjustments — "
        "e.g., 'against this pool, widen your value betting range and cut bluffs.' "
        "Great for pre-session prep at live cash games."
    ),
)
if pool_notes != st.session_state.get("pool_notes", ""):
    st.session_state["pool_notes"] = pool_notes

mode = None
with col1:
    if st.button("⚡ Fast\n\nLLM-only · ~10s", use_container_width=True):
        mode = "fast"
with col2:
    if st.button("🎯 Default\n\nSolver · ~1-2 min", use_container_width=True, type="primary"):
        mode = "default"
with col3:
    if st.button("🏆 Pro\n\nHigh accuracy · ~4-6 min", use_container_width=True):
        mode = "pro"


# ──────────────────────────────────────────────
# Analysis Execution
# ──────────────────────────────────────────────
if mode:
    if not query.strip():
        st.warning("Please describe a poker hand first.")
        st.stop()

    # ── Security checks ──────────────────────────
    session_id = st.session_state["session_id"]

    # Cooldown
    allowed, remaining = check_cooldown(session_id)
    if not allowed:
        st.warning(f"Please wait {remaining:.0f} seconds between requests.")
        st.stop()

    # Input sanitization
    query, input_warnings = sanitize_input(query)
    for w in input_warnings:
        st.warning(w)
    if not query.strip():
        st.stop()

    # Per-session rate limit
    allowed, msg = check_rate_limit(session_id)
    if not allowed:
        st.error(f"🚫 {msg}")
        st.stop()

    # Global rate limit
    allowed, msg = check_global_rate_limit()
    if not allowed:
        st.error(f"🚫 {msg}")
        st.stop()

    # Daily budget
    within_budget, budget_remaining = check_daily_budget()
    if not within_budget:
        st.error("🚫 Daily usage limit reached. Please try again tomorrow.")
        st.stop()

    # Abuse detection
    is_suspicious, reason = detect_abuse(session_id, query)
    if is_suspicious:
        st.error(f"🚫 Request blocked: {reason}")
        st.stop()

    # ── Auth / free-tier gate ────────────────────
    if not st.session_state.get("authenticated"):
        free_uses = st.session_state.get("free_uses", 0)
        allowed, remaining = check_free_tier(free_uses)
        if not allowed:
            st.warning(
                "🔒 **Free use exhausted.** Sign in (sidebar) for unlimited daily access."
            )
            st.stop()
        # Will be incremented after successful analysis
    else:
        # Authenticated user — check their personal daily limit
        _user_email = st.session_state["user_email"]
        _user_ok, _user_remaining = check_user_daily_limit(_user_email)
        if not _user_ok:
            st.error("🚫 You've reached your daily limit. Try again tomorrow.")
            st.stop()

    # Track session usage
    st.session_state["request_count"] = st.session_state.get("request_count", 0) + 1

    if not config.GEMINI_API_KEY:
        st.error("**GEMINI_API_KEY not set.** Follow the steps below to configure it.")
        st.markdown("""
**Local development (`.env` file):**
1. Copy `.env.example` to `.env` in the project root.
2. Add your key: `GEMINI_API_KEY=AIza...`
3. Get a free key at [Google AI Studio](https://aistudio.google.com/apikey).

**Streamlit Community Cloud:**
1. Go to your app's **Settings → Secrets**.
2. Add: `GEMINI_API_KEY = "AIza..."`

See `.streamlit/secrets.toml.example` for the template.
        """)
        st.stop()

    if mode in ("default", "pro") and not solver_ok:
        st.warning("Solver not available. Falling back to LLM-only mode.")

    mode_labels = {
        "fast": "⚡ Fast (LLM-only)",
        "default": "🎯 Default (Solver)",
        "pro": "🏆 Pro (High Accuracy)",
    }

    # Progress / status widget
    status_container = st.status(f"Analyzing with {mode_labels[mode]}...", expanded=True)
    progress_bar = st.progress(0, text="Starting analysis...")

    est_lo, est_hi = _MODE_EST_SECONDS.get(mode, (30, 60))
    st.caption(f"Estimated time: ~{est_lo}-{est_hi}s")

    _progress_state = {"value": 0.0}

    def on_status(msg: str) -> None:
        status_container.write(msg)
        step_key = _detect_step(msg)
        if step_key and step_key in _STEP_PROGRESS:
            start, end = _STEP_PROGRESS[step_key]
            # If the message contains a checkmark, jump to end of this step
            if "\u2713" in msg or "\u2717" in msg or "✓" in msg:
                target = end
            else:
                target = start
            if target > _progress_state["value"]:
                _progress_state["value"] = target
                progress_bar.progress(
                    min(_progress_state["value"], 1.0),
                    text=msg[:80],
                )

    from poker_gpt.main import _combine_opponent_pool_notes

    t0 = time.time()

    combined_notes = _combine_opponent_pool_notes(opponent_notes, pool_notes)

    try:
        result = analyze_hand(
            query,
            mode=mode,
            on_status=on_status,
            opponent_notes=combined_notes,
        )
        elapsed = time.time() - t0

        progress_bar.progress(1.0, text=f"✅ Complete in {elapsed:.1f}s")
        status_container.update(
            label=f"✅ Analysis complete in {elapsed:.1f}s",
            state="complete",
        )

        # Record daily usage after a successful analysis
        record_daily_usage()

        # Track auth: increment free uses or record user usage
        if not st.session_state.get("authenticated"):
            st.session_state["free_uses"] = st.session_state.get("free_uses", 0) + 1
        else:
            record_user_usage(st.session_state["user_email"])

        # ── Results Section ──
        st.divider()

        # Metrics row
        if result.get("scenario"):
            scenario = result["scenario"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Hand", scenario.hero_hand)
            m2.metric("Board", scenario.board.replace(",", " ") if scenario.board else "—")
            m3.metric("Pot", f"{scenario.pot_size_bb:.0f}bb")
            m4.metric("Stack", f"{scenario.effective_stack_bb:.0f}bb")

        # Strategy visualization
        if result.get("strategy"):
            strategy = result["strategy"]
            st.subheader("📊 Strategy")

            if result.get("cached"):
                st.info("📦 Loaded from cache (instant)")

            for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
                pct = freq * 100
                bar_col, pct_col = st.columns([5, 1])
                bar_col.progress(min(freq, 1.0), text=action)
                pct_col.markdown(f"**{pct:.1f}%**")

            st.caption(
                f"Best action: **{strategy.best_action}** "
                f"({strategy.best_action_freq * 100:.1f}%)"
            )

        # Sanity note
        if result.get("sanity_note"):
            st.subheader("🔍 Sanity Check")
            note = result["sanity_note"]
            if note.startswith("✅"):
                st.success(note)
            elif note.startswith("⚠️"):
                st.warning(note)
            else:
                st.info(note)

        # Advice
        st.subheader("🎯 Advice")
        st.markdown(result.get("advice", "No advice generated."))

        # Footer
        source_label = result.get("source", "unknown")
        if result.get("cached"):
            source_label += " (cached)"
        # Confidence badge
        confidence = result.get("confidence", "low")
        conf_colors = {
            "high": "green", "medium": "orange", "low": "red",
        }
        conf_labels = {
            "high": "High \u2014 solver-verified",
            "medium": "Medium \u2014 pre-solved GTO lookup",
            "low": "Low \u2014 LLM approximation",
        }
        conf_color = conf_colors.get(confidence, "gray")
        conf_text = conf_labels.get(confidence, confidence)
        st.markdown(
            f"**Confidence:** :{conf_color}[{conf_text}]"
        )
        # Trust badge
        badge = get_source_badge(result.get("source", "unknown"))
        if badge:
            st.markdown(f"**{badge}**")

        # Spot frequency
        spot_freq = result.get("spot_frequency")
        if spot_freq:
            with st.expander(
                f"📊 Spot Frequency: ~{spot_freq.frequency_pct}% of all hands "
                f"({spot_freq.priority_label})",
                expanded=False,
            ):
                st.write(spot_freq.note)
                if spot_freq.similar_spots:
                    st.write("**Also study:**")
                    for s in spot_freq.similar_spots[:3]:
                        st.write(f"• {s}")

        st.caption(
            f"Mode: {mode_labels[mode]} · "
            f"Time: {elapsed:.1f}s · "
            f"Source: {source_label}"
        )

    except Exception as e:
        elapsed = time.time() - t0
        progress_bar.progress(1.0, text=f"❌ Error after {elapsed:.1f}s")
        status_container.update(
            label=f"❌ Error after {elapsed:.1f}s",
            state="error",
        )
        st.error(f"Analysis failed: {e}")
        if config.DEBUG:
            import traceback
            st.code(traceback.format_exc())
