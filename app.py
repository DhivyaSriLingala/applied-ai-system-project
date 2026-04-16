import os
import random

import streamlit as st

from logic_utils import (
    get_range_for_difficulty,
    parse_guess,
    check_guess,
    update_score,
)
from logger_config import setup_logger

st.set_page_config(
    page_title="Game Glitch Investigator + AI Bug Inspector",
    page_icon="🎮",
    layout="wide",
)

logger = setup_logger("app")

tab_game, tab_ai = st.tabs(["🎮 Glitchy Guesser", "🔍 AI Bug Inspector"])

# ==========================================================================
# TAB 1 — Original number-guessing game (unchanged logic)
# ==========================================================================
with tab_game:
    st.title("🎮 Game Glitch Investigator")
    st.caption("An AI-generated guessing game. Something is off.")

    st.sidebar.header("Settings")
    difficulty = st.sidebar.selectbox("Difficulty", ["Easy", "Normal", "Hard"], index=1)

    attempt_limit_map = {"Easy": 6, "Normal": 8, "Hard": 5}
    attempt_limit = attempt_limit_map[difficulty]

    low, high = get_range_for_difficulty(difficulty)
    st.sidebar.caption(f"Range: {low} to {high}")
    st.sidebar.caption(f"Attempts allowed: {attempt_limit}")

    if "secret" not in st.session_state:
        st.session_state.secret = random.randint(low, high)
    if "attempts" not in st.session_state:
        st.session_state.attempts = 0
    if "score" not in st.session_state:
        st.session_state.score = 0
    if "status" not in st.session_state:
        st.session_state.status = "playing"
    if "history" not in st.session_state:
        st.session_state.history = []

    st.subheader("Make a guess")

    st.info(
        f"Guess a number between {low} and {high}. "
        f"Attempts left: {attempt_limit - st.session_state.attempts}"
    )

    with st.expander("Developer Debug Info"):
        st.write("Secret:", st.session_state.secret)
        st.write("Attempts:", st.session_state.attempts)
        st.write("Score:", st.session_state.score)
        st.write("Difficulty:", difficulty)
        st.write("History:", st.session_state.history)

    raw_guess = st.text_input("Enter your guess:", key=f"guess_input_{difficulty}")

    col1, col2, col3 = st.columns(3)
    with col1:
        submit = st.button("Submit Guess 🚀")
    with col2:
        new_game = st.button("New Game 🔁")
    with col3:
        show_hint = st.checkbox("Show hint", value=True)

    if new_game:
        st.session_state.attempts = 0
        st.session_state.secret = random.randint(low, high)
        st.session_state.status = "playing"
        st.session_state.history = []
        st.success("New game started.")
        st.rerun()

    if st.session_state.status != "playing":
        if st.session_state.status == "won":
            st.success("You already won. Start a new game to play again.")
        else:
            st.error("Game over. Start a new game to try again.")
        st.stop()

    if submit:
        st.session_state.attempts += 1
        ok, guess_int, err = parse_guess(raw_guess)

        if not ok:
            st.session_state.history.append(raw_guess)
            st.error(err)
        else:
            st.session_state.history.append(guess_int)
            outcome, message = check_guess(guess_int, st.session_state.secret)

            if show_hint:
                st.warning(message)

            st.session_state.score = update_score(
                current_score=st.session_state.score,
                outcome=outcome,
                attempt_number=st.session_state.attempts,
            )

            if outcome == "Win":
                st.balloons()
                st.session_state.status = "won"
                st.success(
                    f"You won! The secret was {st.session_state.secret}. "
                    f"Final score: {st.session_state.score}"
                )
            else:
                if st.session_state.attempts >= attempt_limit:
                    st.session_state.status = "lost"
                    st.error(
                        f"Out of attempts! "
                        f"The secret was {st.session_state.secret}. "
                        f"Score: {st.session_state.score}"
                    )

    st.divider()
    st.caption("Built by an AI that claims this code is production-ready.")

# ==========================================================================
# TAB 2 — AI Bug Inspector (RAG + Agentic workflow)
# ==========================================================================
with tab_ai:
    st.title("🔍 AI Bug Inspector")
    st.caption(
        "Paste Python code and let the AI agent diagnose and fix bugs using "
        "RAG-augmented multi-step reasoning."
    )

    # --- Sidebar: agent mode toggle ---
    agent_mode = st.sidebar.radio(
        "Agent Mode",
        ["Standard", "Few-Shot"],
        index=0,
        help=(
            "Standard: zero-shot bug classification.\n"
            "Few-Shot: 3 worked examples injected into the Plan step for "
            "more structured, consistent output."
        ),
    )

    st.info(
        "**How it works (4 observable steps):**\n\n"
        "0. **RAG** — top-3 docs retrieved from the knowledge base; injected into every prompt.\n"
        "1. **Plan** — Claude classifies the bug type.\n"
        "2. **Diagnose** — Claude performs a deep line-level analysis + self-rates confidence.\n"
        "3. **Fix** — Claude generates corrected code.\n"
        "4. **Verify** — Claude compares original vs fixed and issues a VERIFIED / "
        "NEEDS_REVIEW / UNCERTAIN verdict.\n\n"
        "Set `ANTHROPIC_API_KEY` in your environment before running.",
        icon="ℹ️",
    )

    code_input = st.text_area(
        "Paste your Python code here:",
        height=280,
        placeholder=(
            "# Example — paste any buggy Python snippet\n"
            "def check_guess(guess, secret):\n"
            "    secret = str(secret)  # bug: type mismatch\n"
            "    if guess == secret:\n"
            "        return 'Win'\n"
            "    elif guess > secret:\n"
            "        return 'Too High'\n"
            "    else:\n"
            "        return 'Too Low'\n"
        ),
    )

    desc_input = st.text_input(
        "Describe the problem (optional):",
        placeholder="e.g. The game never detects a win even when I type the exact number.",
    )

    analyze = st.button("🤖 Analyze & Fix", type="primary")

    if analyze:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error(
                "**ANTHROPIC_API_KEY is not set.** "
                "Export it in your terminal before starting Streamlit:\n\n"
                "```\nexport ANTHROPIC_API_KEY=sk-ant-...\n```"
            )
        else:
            logger.info(
                "AI Bug Inspector triggered | mode=%s | code_len=%d",
                agent_mode, len(code_input),
            )

            # Instantiate agent based on mode selection
            if agent_mode == "Few-Shot":
                from few_shot_agent import FewShotDebuggingAgent
                agent = FewShotDebuggingAgent()
                st.caption(f"Mode: {FewShotDebuggingAgent.describe_mode()}")
            else:
                from ai_agent import DebuggingAgent
                agent = DebuggingAgent()

            # --- Step-by-step execution with progressive UI ---
            status_text = st.empty()

            # Guardrail check first (no API call)
            valid, err_msg = agent._validate_input(code_input)
            if not valid:
                st.error(f"**Input rejected:** {err_msg}")
                logger.warning("Guardrail rejected input: %s", err_msg)
            else:
                # Step 0 — RAG retrieval
                status_text.info("Step 0 / 4 — Retrieving relevant documentation...")
                context_chunks, context_text = agent.retrieve(code_input, desc_input)

                with st.expander(
                    f"📚 Step 0 — Retrieved Knowledge Base Context"
                    f" ({len(context_chunks)} chunks)",
                    expanded=False,
                ):
                    if context_chunks:
                        st.caption(
                            "These chunks were injected into every Claude prompt. "
                            "They ground the AI's reasoning in documented patterns."
                        )
                        for i, chunk in enumerate(context_chunks, 1):
                            st.markdown(f"**Chunk {i}:**")
                            st.text(chunk[:500] + ("..." if len(chunk) > 500 else ""))
                            if i < len(context_chunks):
                                st.divider()
                    else:
                        st.caption("No relevant chunks found for this query.")

                # Step 1 — Plan
                status_text.info("Step 1 / 4 — Classifying bug type (Plan)...")
                try:
                    plan = agent.step_plan(code_input, desc_input, context_text)
                except Exception as exc:
                    st.error(f"Plan step failed: {exc}")
                    logger.error("Plan step error: %s", exc)
                    st.stop()

                with st.expander("📋 Step 1 — Bug Classification (Plan)", expanded=True):
                    st.info(plan)

                # Step 2 — Diagnose
                status_text.info("Step 2 / 4 — Diagnosing exact bug location...")
                try:
                    raw_diag = agent.step_diagnose(
                        code_input, desc_input, context_text, plan
                    )
                    diagnosis, confidence, confidence_reason = agent._parse_confidence(raw_diag)
                except Exception as exc:
                    st.error(f"Diagnose step failed: {exc}")
                    logger.error("Diagnose step error: %s", exc)
                    st.stop()

                with st.expander("🔬 Step 2 — Detailed Diagnosis", expanded=True):
                    st.warning(diagnosis)
                    if confidence is not None:
                        conf_color = (
                            "green" if confidence >= 0.80
                            else "orange" if confidence >= 0.55
                            else "red"
                        )
                        st.markdown(
                            f"**Confidence:** :{conf_color}[{confidence:.0%}]"
                            f"  —  *{confidence_reason}*"
                        )

                # Step 3 — Fix
                status_text.info("Step 3 / 4 — Generating corrected code...")
                try:
                    fixed_code = agent.step_fix(code_input, diagnosis)
                except Exception as exc:
                    st.error(f"Fix step failed: {exc}")
                    logger.error("Fix step error: %s", exc)
                    st.stop()

                with st.expander("🔧 Step 3 — Fixed Code", expanded=True):
                    st.markdown(fixed_code)

                # Step 4 — Verify
                status_text.info("Step 4 / 4 — Verifying the fix...")
                try:
                    raw_verify   = agent.step_verify(code_input, fixed_code, diagnosis)
                    verification = agent._parse_verify(raw_verify)
                except Exception as exc:
                    st.error(f"Verify step failed: {exc}")
                    logger.error("Verify step error: %s", exc)
                    st.stop()

                verdict       = verification["verdict"]
                verdict_emoji = {"VERIFIED": "✅", "NEEDS_REVIEW": "⚠️"}.get(verdict, "❓")
                verdict_color = {
                    "VERIFIED": "green", "NEEDS_REVIEW": "orange"
                }.get(verdict, "red")

                with st.expander(
                    f"{verdict_emoji} Step 4 — Verification: {verdict}", expanded=True
                ):
                    st.markdown(
                        f"**Verdict:** :{verdict_color}[{verdict}]  |  "
                        f"**Addresses Bug:** {verification['addresses_bug']}  |  "
                        f"**New Issues:** {verification['new_issues']}"
                    )
                    st.caption(verification["explanation"])

                status_text.success(
                    f"Analysis complete — {verdict_emoji} {verdict}"
                )
                logger.info(
                    "AI Bug Inspector complete | verdict=%s | confidence=%.2f",
                    verdict, confidence,
                )

    st.divider()
    st.caption(
        "AI Bug Inspector | RAG + Agentic Workflow (Plan→Diagnose→Fix→Verify)"
        " | Standard & Few-Shot modes | Powered by Claude claude-sonnet-4-6"
    )
