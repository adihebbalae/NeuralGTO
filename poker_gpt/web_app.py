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
from poker_gpt.quiz import score_user_action, generate_quiz_feedback, QuizScore
from poker_gpt import config

# Auto-download solver binary on Linux (Streamlit Cloud) if not present
if config.IS_LINUX and not is_solver_available():
    config.ensure_solver_binary()

from poker_gpt.security import (
    check_rate_limit,
    check_global_rate_limit,
    check_cooldown,
    sanitize_input,
    check_daily_budget,
    detect_abuse,
    record_daily_usage,
    get_client_ip,
    check_anon_limit,
    record_anon_use,
    MAX_REQUESTS_PER_SESSION,
    ANON_DAILY_LIMIT,
)
from poker_gpt.auth import (
    register,
    login,
    check_login_lockout,
    record_user_usage,
    check_user_daily_limit,
    get_user_stats,
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

# Client IP for rate limiting (persists across page refreshes, unlike session_id)
_client_ip = get_client_ip()

# ── Debug mode production guard ──
if config.DEBUG:
    st.warning(
        "⚠️ **DEBUG MODE IS ON** — Stack traces and verbose logging are visible. "
        "Set `POKERGPT_DEBUG=false` before deploying to production.",
        icon="🔓",
    )

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
        _, _free_left = check_anon_limit(_client_ip)
        st.markdown(f"**Free uses left:** {_free_left} / {ANON_DAILY_LIMIT} today")
        st.caption("Sign in for more daily analyses.")
        _auth_tab = st.radio("", ["Sign in", "Register"], horizontal=True, label_visibility="collapsed")
        _auth_email = st.text_input("Email", key="auth_email")
        _auth_pass = st.text_input("Password", type="password", key="auth_pass")
        if _auth_tab == "Sign in":
            if st.button("Sign in", use_container_width=True, type="primary"):
                # Brute-force lockout check before attempting login
                _lockout_ok, _lockout_wait = check_login_lockout(_client_ip)
                if not _lockout_ok:
                    st.error(f"Too many login attempts. Try again in {_lockout_wait // 60 + 1} minutes.")
                else:
                    ok, msg = login(_auth_email, _auth_pass, client_ip=_client_ip)
                    if ok:
                        st.session_state["authenticated"] = True
                        st.session_state["user_email"] = _auth_email.strip().lower()
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            if st.button("Create account", use_container_width=True, type="primary"):
                ok, msg = register(_auth_email, _auth_pass, client_ip=_client_ip)
                if ok:
                    st.session_state["authenticated"] = True
                    st.session_state["user_email"] = _auth_email.strip().lower()
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()
    st.markdown("### 🎓 Output Level")
    output_level = st.radio(
        "Output level",
        options=["advanced", "beginner"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        help=(
            "**Advanced:** Full GTO analysis with frequencies, range logic, "
            "blocker effects, and mixed strategy resolution.\n\n"
            "**Beginner:** One clear action with plain-language reasoning. "
            "No jargon, no percentages — just what to do and why."
        ),
    )
    if output_level == "beginner":
        st.caption("Plain-language coaching — no jargon.")
    else:
        st.caption("Full GTO breakdown with frequencies.")

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
# App Mode Toggle — Analyzer vs Quiz
# ──────────────────────────────────────────────
app_mode = st.radio(
    "App mode",
    options=["🎯 Analyzer", "🧠 Quiz Mode"],
    horizontal=True,
    label_visibility="collapsed",
    help=(
        "**Analyzer:** Get full GTO advice on any poker spot.\n\n"
        "**Quiz Mode:** Test yourself! Describe a spot, guess the action, "
        "then see how your decision compares to GTO."
    ),
)
_is_quiz = app_mode.startswith("🧠")

# Initialize quiz session state
if "quiz_state" not in st.session_state:
    st.session_state["quiz_state"] = "idle"       # idle → guessing → revealed
    st.session_state["quiz_result"] = None         # analyze_hand result (hidden)
    st.session_state["quiz_score"] = None          # QuizScore object
    st.session_state["quiz_feedback"] = None       # LLM coaching text
    st.session_state["quiz_history"] = []          # list of past quiz scores


# ──────────────────────────────────────────────
# Example queries (quick-start)
# ──────────────────────────────────────────────
EXAMPLES = [
    "I have QQ on the button, flop is Ts 9d 4h, villain checks. Pot is 20bb, stacks are 90bb.",
    "I have AKs in the CO, BTN 3bets to 9bb. 100bb effective. What do I do?",
    "I hold 87s on the BB, SB opens to 3bb. Flop is 6h 5d 2c, SB bets 2bb into 6bb pot.",
]

if not _is_quiz:
    with st.expander("💡 Example hands (click to try)"):
        for ex in EXAMPLES:
            if st.button(ex, key=f"ex_{hash(ex)}", use_container_width=True):
                st.session_state["query"] = ex
else:
    with st.expander("💡 Quiz examples — try these spots"):
        for ex in EXAMPLES:
            if st.button(ex, key=f"qex_{hash(ex)}", use_container_width=True):
                st.session_state["query"] = ex
                st.session_state["quiz_state"] = "idle"


# ──────────────────────────────────────────────
# Hand History Import (Analyzer only)
# ──────────────────────────────────────────────
if not _is_quiz:
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
            # T7: Cap uploaded file size to prevent memory abuse
            _MAX_UPLOAD_BYTES = 512 * 1024  # 512 KB
            hh_file.seek(0, 2)  # seek to end
            _file_size = hh_file.tell()
            hh_file.seek(0)     # reset to start
            if _file_size > _MAX_UPLOAD_BYTES:
                st.error(f"File too large ({_file_size // 1024} KB). Maximum is {_MAX_UPLOAD_BYTES // 1024} KB.")
            else:
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
    "🃏 Describe your poker hand:" if not _is_quiz else "🧠 Describe a poker spot to quiz yourself:",
    value=st.session_state.get("query", ""),
    placeholder="Example: I have QQ on the button, the flop is Ts 9d 4h, "
                "villain checks to me. Pot is 20bb, stacks are 90bb.",
    height=120,
)

if not _is_quiz:
    # ──────────────────────────────────────────
    # ANALYZER MODE — mode selection + notes
    # ──────────────────────────────────────────
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
else:
    # ──────────────────────────────────────────
    # QUIZ MODE — quiz controls
    # ──────────────────────────────────────────
    opponent_notes = ""
    pool_notes = ""
    mode = None

    quiz_state = st.session_state.get("quiz_state", "idle")

    if quiz_state == "idle":
        st.markdown("**Choose quiz difficulty:**")
        qcol1, qcol2 = st.columns(2)
        with qcol1:
            if st.button("⚡ Quick Quiz\n\nLLM-only", use_container_width=True):
                mode = "fast"
                st.session_state["quiz_mode_used"] = "fast"
        with qcol2:
            if st.button("🎯 Solver Quiz\n\nGTO-verified", use_container_width=True, type="primary"):
                mode = "default"
                st.session_state["quiz_mode_used"] = "default"

    elif quiz_state == "guessing":
        # Show scenario metrics but hide strategy/advice
        qr = st.session_state.get("quiz_result")
        if qr and qr.get("scenario"):
            scenario = qr["scenario"]
            st.divider()
            st.subheader("📋 The Spot")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Hand", scenario.hero_hand)
            m2.metric("Board", scenario.board.replace(",", " ") if scenario.board else "Preflop")
            m3.metric("Pot", f"{scenario.pot_size_bb:.0f}bb")
            m4.metric("Stack", f"{scenario.effective_stack_bb:.0f}bb")

            pos_label = scenario.hero_position
            if scenario.hero_is_ip:
                pos_label += " (IP)"
            else:
                pos_label += " (OOP)"
            st.markdown(f"**Position:** {pos_label} · **Street:** {scenario.current_street.title()}")

        st.divider()
        st.subheader("🤔 What's your play?")
        st.caption("Type your action: fold, check, call, bet [size], raise [size], all-in")

        user_guess = st.text_input(
            "Your action:",
            value="",
            placeholder="e.g. bet 67, check, raise, fold",
            key="quiz_guess_input",
        )

        if st.button("✅ Submit Answer", type="primary", use_container_width=True):
            if not user_guess.strip():
                st.warning("Please type an action first.")
            else:
                # Score the answer
                strategy = qr["strategy"]
                if strategy is None:
                    st.error("No strategy available to score against. Try a different spot.")
                else:
                    qs = score_user_action(user_guess, strategy)
                    st.session_state["quiz_score"] = qs
                    st.session_state["quiz_state"] = "revealed"

                    # Generate coaching feedback
                    try:
                        feedback = generate_quiz_feedback(
                            scenario=qr["scenario"],
                            strategy=strategy,
                            quiz_score=qs,
                            output_level=output_level,
                        )
                        st.session_state["quiz_feedback"] = feedback
                    except Exception as e:
                        st.session_state["quiz_feedback"] = (
                            f"_(Coaching feedback unavailable: {e})_"
                        )

                    # Record in history
                    st.session_state["quiz_history"].append({
                        "hand": qr["scenario"].hero_hand if qr.get("scenario") else "?",
                        "score": qs.score,
                        "grade": qs.grade,
                        "user_action": qs.user_action,
                        "gto_action": qs.gto_best_action,
                    })
                    st.rerun()

        if st.button("🔄 New Spot", use_container_width=True):
            st.session_state["quiz_state"] = "idle"
            st.session_state["quiz_result"] = None
            st.session_state["quiz_score"] = None
            st.session_state["quiz_feedback"] = None
            st.rerun()

    elif quiz_state == "revealed":
        # Show score + strategy + coaching feedback
        qs = st.session_state.get("quiz_score")
        qr = st.session_state.get("quiz_result")
        qfeedback = st.session_state.get("quiz_feedback", "")

        if qs and qr:
            st.divider()

            # Score header
            grade_colors = {
                "Perfect": "green",
                "Good": "blue",
                "Acceptable": "orange",
                "Incorrect": "red",
            }
            grade_color = grade_colors.get(qs.grade, "gray")

            st.subheader(f"Score: {qs.score}/100 — :{grade_color}[{qs.grade}]")

            # Comparison metrics
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Your Action", qs.user_action)
            mc2.metric("GTO Best", qs.gto_best_action)
            mc3.metric(
                "GTO Freq of Your Action",
                f"{qs.gto_freq_of_user_action * 100:.1f}%",
            )

            if qs.is_mixed_spot:
                st.info("ℹ️ This is a **mixed strategy** spot — GTO uses multiple actions.")

            # Show scenario metrics
            if qr.get("scenario"):
                scenario = qr["scenario"]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Hand", scenario.hero_hand)
                m2.metric("Board", scenario.board.replace(",", " ") if scenario.board else "Preflop")
                m3.metric("Pot", f"{scenario.pot_size_bb:.0f}bb")
                m4.metric("Stack", f"{scenario.effective_stack_bb:.0f}bb")

            # Strategy bars
            if qr.get("strategy"):
                strategy = qr["strategy"]
                st.subheader("📊 GTO Strategy")
                for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
                    pct = freq * 100
                    bar_col, pct_col = st.columns([5, 1])
                    bar_col.progress(min(freq, 1.0), text=action)
                    pct_col.markdown(f"**{pct:.1f}%**")

            # Coaching feedback
            st.subheader("🎓 Coaching")
            st.markdown(qfeedback)

        # New quiz button
        if st.button("🔄 New Spot", type="primary", use_container_width=True, key="quiz_new"):
            st.session_state["quiz_state"] = "idle"
            st.session_state["quiz_result"] = None
            st.session_state["quiz_score"] = None
            st.session_state["quiz_feedback"] = None
            st.rerun()

        # Session stats
        history = st.session_state.get("quiz_history", [])
        if len(history) > 1:
            with st.expander(f"📊 Session Stats ({len(history)} quizzes)"):
                avg_score = sum(h["score"] for h in history) / len(history)
                perfect_count = sum(1 for h in history if h["grade"] == "Perfect")
                st.markdown(
                    f"**Average Score:** {avg_score:.0f}/100 · "
                    f"**Perfect:** {perfect_count}/{len(history)}"
                )
                for i, h in enumerate(reversed(history), 1):
                    grade_c = grade_colors.get(h["grade"], "gray")
                    st.markdown(
                        f"{i}. {h['hand']} — :{grade_c}[{h['grade']}] "
                        f"({h['score']}/100) · You: {h['user_action']} → GTO: {h['gto_action']}"
                    )


# ──────────────────────────────────────────────
# Analysis Execution
# ──────────────────────────────────────────────
if mode:
    if not query.strip():
        st.warning("Please describe a poker hand first.")
        st.stop()

    # ── Security checks (keyed on IP, not session — survives refresh) ──

    # Cooldown
    allowed, remaining = check_cooldown(_client_ip)
    if not allowed:
        st.warning(f"Please wait {remaining:.0f} seconds between requests.")
        st.stop()

    # Input sanitization — main query
    query, input_warnings = sanitize_input(query)
    for w in input_warnings:
        st.warning(w)
    if not query.strip():
        st.stop()

    # T5: Sanitize opponent/pool notes (these also go to Gemini)
    if opponent_notes:
        opponent_notes, _opp_warns = sanitize_input(opponent_notes, max_length=500)
        for w in _opp_warns:
            st.warning(f"Opponent notes: {w}")
    if pool_notes:
        pool_notes, _pool_warns = sanitize_input(pool_notes, max_length=500)
        for w in _pool_warns:
            st.warning(f"Pool notes: {w}")

    # Per-IP rate limit (replaces per-session — can't be bypassed by refresh)
    allowed, msg = check_rate_limit(_client_ip)
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
    is_suspicious, reason = detect_abuse(_client_ip, query)
    if is_suspicious:
        st.error(f"🚫 Request blocked: {reason}")
        st.stop()

    # ── Auth / free-tier gate (IP-based, survives page refresh) ──
    if not st.session_state.get("authenticated"):
        allowed, remaining = check_anon_limit(_client_ip)
        if not allowed:
            st.warning(
                "🔒 **Free daily uses exhausted.** "
                "Sign in or create an account (sidebar) for more analyses."
            )
            st.stop()
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
            output_level=output_level,
        )
        elapsed = time.time() - t0

        progress_bar.progress(1.0, text=f"✅ Complete in {elapsed:.1f}s")
        status_container.update(
            label=f"✅ Analysis complete in {elapsed:.1f}s",
            state="complete",
        )

        # Record daily usage after a successful analysis
        record_daily_usage()

        # Track auth: record anonymous IP usage or authenticated user usage
        if not st.session_state.get("authenticated"):
            record_anon_use(_client_ip)
        else:
            record_user_usage(st.session_state["user_email"])

        # ── Quiz Mode: store result silently and transition to guessing ──
        if _is_quiz:
            st.session_state["quiz_result"] = result
            st.session_state["quiz_state"] = "guessing"
            st.rerun()

        # ── Results Section (Analyzer mode only) ──
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
