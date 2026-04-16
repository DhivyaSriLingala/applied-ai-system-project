"""
Agentic debugging workflow powered by Claude and RAG.

The DebuggingAgent runs three sequential Claude API calls:
  1. Plan   — classify the type of bug present in the code
  2. Diagnose — perform a detailed line-by-line analysis using the plan
  3. Fix    — generate corrected code based on the diagnosis

At every step, relevant documentation retrieved via RAGEngine is injected into
the prompt so Claude reasons over domain-specific knowledge rather than
relying on general training alone.

Guardrails
----------
- Empty or whitespace-only code is rejected before any API call.
- Code exceeding MAX_CODE_CHARS is rejected to prevent runaway token usage.
- API errors are caught and surfaced as structured error dicts so the UI
  never crashes from an unhandled exception.

Logging
-------
Every API call is logged with step name, latency (seconds), and response size.
Full responses are written at DEBUG level so the log file contains a complete
audit trail while the console stays readable.
"""

import os
import time
import logging

import anthropic

from logger_config import setup_logger
from rag_engine import RAGEngine

logger = setup_logger("ai_bug_inspector")

MAX_CODE_CHARS = 5_000
MIN_CODE_CHARS = 5
MODEL = "claude-sonnet-4-6"


class DebuggingAgent:
    """Three-step agentic debugger: Plan → Diagnose → Fix."""

    def __init__(self):
        self.rag = RAGEngine()
        # anthropic.Anthropic() reads ANTHROPIC_API_KEY from the environment automatically
        self.client = anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Guardrails
    # ------------------------------------------------------------------

    def _validate_input(self, code: str) -> tuple[bool, str]:
        """Return (is_valid, error_message). Called before any API usage."""
        stripped = (code or "").strip()
        if not stripped:
            return False, "Code cannot be empty."
        if len(stripped) < MIN_CODE_CHARS:
            return False, "Code is too short to analyze meaningfully."
        if len(code) > MAX_CODE_CHARS:
            return (
                False,
                f"Code exceeds the {MAX_CODE_CHARS:,}-character limit. "
                "Paste a smaller excerpt.",
            )
        return True, ""

    # ------------------------------------------------------------------
    # Claude API wrapper
    # ------------------------------------------------------------------

    def _call_claude(self, system: str, user: str, step_name: str) -> str:
        """
        Send a single-turn message to Claude and return the text response.
        Logs latency and response length at INFO; full output at DEBUG.
        """
        logger.info("[%s] Calling Claude (%s)", step_name, MODEL)
        start = time.time()

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        elapsed = time.time() - start
        text = response.content[0].text
        logger.info(
            "[%s] Response in %.2fs | %d chars | %d input tokens | %d output tokens",
            step_name,
            elapsed,
            len(text),
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        logger.debug("[%s] Full response:\n%s", step_name, text)
        return text

    # ------------------------------------------------------------------
    # Agentic workflow steps
    # ------------------------------------------------------------------

    def _step_plan(self, code: str, description: str, context_text: str) -> str:
        return self._call_claude(
            system=(
                "You are an expert Python debugger. Your job is to classify the type of "
                "bug present in code.\n"
                "Output 2–3 sentences: name the bug category, explain the mechanism, "
                "and cite which part of the code is suspicious."
            ),
            user=(
                f"RELEVANT DOCUMENTATION:\n{context_text}\n\n"
                f"USER DESCRIPTION: {description or 'No description provided.'}\n\n"
                f"CODE:\n```python\n{code}\n```\n\n"
                "What type of bug is most likely present?"
            ),
            step_name="PLAN",
        )

    def _step_diagnose(
        self, code: str, description: str, context_text: str, plan: str
    ) -> str:
        return self._call_claude(
            system=(
                "You are an expert Python debugger performing a deep diagnosis.\n"
                "Given a preliminary bug classification, identify the exact line(s) causing "
                "the bug, explain WHY the code fails, and describe what correct behavior "
                "should look like."
            ),
            user=(
                f"RELEVANT DOCUMENTATION:\n{context_text}\n\n"
                f"USER DESCRIPTION: {description or 'No description provided.'}\n\n"
                f"CODE:\n```python\n{code}\n```\n\n"
                f"PRELIMINARY CLASSIFICATION:\n{plan}\n\n"
                "Perform a detailed diagnosis. Cite line numbers where possible."
            ),
            step_name="DIAGNOSE",
        )

    def _step_fix(self, code: str, diagnosis: str) -> str:
        return self._call_claude(
            system=(
                "You are an expert Python debugger. Given a diagnosis, produce the corrected "
                "version of the code.\n"
                "Output the fixed Python code in a ```python ... ``` block, followed by a "
                "brief bulleted list of changes made."
            ),
            user=(
                f"ORIGINAL CODE:\n```python\n{code}\n```\n\n"
                f"DIAGNOSIS:\n{diagnosis}\n\n"
                "Provide the fixed code and list of changes."
            ),
            step_name="FIX",
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, code: str, description: str = "") -> dict:
        """
        Run the full Plan → Diagnose → Fix pipeline.

        Returns a dict with keys:
            error       — str if a guardrail or API error occurred, else None
            plan        — str output of the planning step
            diagnosis   — str output of the diagnosis step
            fixed_code  — str output of the fix step
            context     — list[str] of RAG chunks injected into the prompts
        """
        logger.info(
            "DebuggingAgent.run() | code_len=%d | desc=%r",
            len(code),
            description,
        )

        # Step 0: Guardrail validation
        valid, error_msg = self._validate_input(code)
        if not valid:
            logger.warning("Guardrail rejected input: %s", error_msg)
            return {
                "error": error_msg,
                "plan": None,
                "diagnosis": None,
                "fixed_code": None,
                "context": [],
            }

        # Step 1: RAG retrieval — build context injected into every Claude call
        query = f"{description} {code}"
        context_chunks = self.rag.retrieve(query, top_k=3)
        context_text = (
            "\n\n---\n\n".join(context_chunks)
            if context_chunks
            else "No relevant context retrieved."
        )
        logger.info("RAG retrieved %d chunks", len(context_chunks))

        # Steps 2–4: Plan → Diagnose → Fix (each call uses the previous output)
        try:
            plan = self._step_plan(code, description, context_text)
            diagnosis = self._step_diagnose(code, description, context_text, plan)
            fixed_code = self._step_fix(code, diagnosis)
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            return {
                "error": f"Claude API error: {exc}",
                "plan": None,
                "diagnosis": None,
                "fixed_code": None,
                "context": context_chunks,
            }

        logger.info("DebuggingAgent.run() completed successfully")
        return {
            "error": None,
            "plan": plan,
            "diagnosis": diagnosis,
            "fixed_code": fixed_code,
            "context": context_chunks,
        }
