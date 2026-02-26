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
import streamlit as st

from poker_gpt.main import analyze_hand
from poker_gpt.solver_runner import is_solver_available
from poker_gpt.cache import get_cache_stats, clear_cache
from poker_gpt import config


# ──────────────────────────────────────────────
# Page Configuration
# ──────────────────────────────────────────────
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
    st.markdown("""
### Mode Details

**⚡ Fast** — LLM-only approximation (~10s)
Best for quick reads and preflop spots.

**🎯 Default** — Solver low accuracy (~1-2 min)
Good balance of speed vs precision. ~2% of pot exploitability.

**🏆 Pro** — Solver high accuracy (~4-6 min)
Maximum precision. <0.5% of pot exploitability.
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

    if not config.GEMINI_API_KEY:
        st.error("GEMINI_API_KEY not set. Add it to your `.env` file.")
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

    def on_status(msg: str):
        status_container.write(msg)

    t0 = time.time()

    try:
        result = analyze_hand(
            query,
            mode=mode,
            on_status=on_status,
            opponent_notes=opponent_notes,
        )
        elapsed = time.time() - t0

        status_container.update(
            label=f"✅ Analysis complete in {elapsed:.1f}s",
            state="complete",
        )

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
        st.caption(
            f"Mode: {mode_labels[mode]} · "
            f"Time: {elapsed:.1f}s · "
            f"Source: {source_label}"
        )

    except Exception as e:
        elapsed = time.time() - t0
        status_container.update(
            label=f"❌ Error after {elapsed:.1f}s",
            state="error",
        )
        st.error(f"Analysis failed: {e}")
        if config.DEBUG:
            import traceback
            st.code(traceback.format_exc())
