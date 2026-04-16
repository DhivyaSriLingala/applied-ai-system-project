"""
Agentic debugging workflow powered by Claude and RAG.

The DebuggingAgent runs four sequential Claude API calls:
  1. Plan     — classify the type of bug present in the code
  2. Diagnose — perform a detailed line-by-line analysis using the plan;
                also asks Claude to self-report a confidence score (0.0-1.0)
  3. Fix      — generate corrected code based on the diagnosis
  4. Verify   — compare original vs fixed code and issue a structured verdict:
                VERIFIED / NEEDS_REVIEW / UNCERTAIN

Each step is also exposed as a public method (step_plan, step_diagnose,
step_fix, step_verify) so the Streamlit UI can call them individually and
display intermediate results as they arrive, making the reasoning chain
directly observable.

RAG context retrieved before Step 1 is injected into every prompt so Claude
reasons over domain-specific knowledge rather than relying on general training.

Confidence Scoring
------------------
The Diagnose step instructs Claude to append two structured lines:
    CONFIDENCE: <float>
    REASON: <one sentence>
Parsed by _parse_confidence().

Verify Verdict
--------------
The Verify step instructs Claude to output exactly four labelled lines:
    VERDICT: <VERIFIED|NEEDS_REVIEW|UNCERTAIN>
    ADDRESSES_BUG: <YES|NO|PARTIAL>
    NEW_ISSUES: <NONE or brief description>
    EXPLANATION: <one to two sentences>
Parsed by _parse_verify().

Guardrails
----------
- Empty or whitespace-only code is rejected before any API call.
- Code exceeding MAX_CODE_CHARS is rejected to prevent runaway token usage.
- API errors are caught and surfaced as structured error dicts so the UI
  never crashes from an unhandled exception.

Logging
-------
Every API call is logged with step name, latency, and token counts at INFO.
Full responses are written at DEBUG level for a complete audit trail.
"""

import os
import re
import time
import logging

import anthropic

from logger_config import setup_logger
from rag_engine import RAGEngine

logger = setup_logger("ai_bug_inspector")

MAX_CODE_CHARS = 5_000
MIN_CODE_CHARS = 5
MODEL = "claude-sonnet-4-6"

# Confidence parsing
_CONF_RE   = re.compile(r"\nCONFIDENCE:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_REASON_RE = re.compile(r"\nREASON:\s*(.+)", re.IGNORECASE)

# Verify parsing
_VERDICT_RE = re.compile(r"VERDICT:\s*(VERIFIED|NEEDS_REVIEW|UNCERTAIN)", re.IGNORECASE)
_ADDR_RE    = re.compile(r"ADDRESSES_BUG:\s*(YES|NO|PARTIAL)", re.IGNORECASE)
_NEWISS_RE  = re.compile(r"NEW_ISSUES:\s*(.+)", re.IGNORECASE)
_EXPL_RE    = re.compile(r"EXPLANATION:\s*(.+)", re.IGNORECASE)


class DebuggingAgent:
    """Four-step agentic debugger: Plan -> Diagnose -> Fix -> Verify."""

    def __init__(self):
        self.rag = RAGEngine()
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
        """Single-turn Claude call. Logs latency and token counts."""
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
            "[%s] %.2fs | %d chars | in=%d out=%d tokens",
            step_name, elapsed, len(text),
            response.usage.input_tokens, response.usage.output_tokens,
        )
        logger.debug("[%s] Full response:\n%s", step_name, text)
        return text

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_confidence(self, text: str) -> tuple[str, float, str]:
        """
        Extract CONFIDENCE / REASON from a Diagnose response.
        Returns (clean_text, score, reason).
        """
        conf_match   = _CONF_RE.search(text)
        reason_match = _REASON_RE.search(text)

        score = max(0.0, min(1.0, float(conf_match.group(1)))) if conf_match else 0.5
        if not conf_match:
            logger.warning("CONFIDENCE line not found; defaulting to 0.5")

        reason = reason_match.group(1).strip() if reason_match else "Not provided"

        clean = _CONF_RE.sub("", text)
        clean = _REASON_RE.sub("", clean).strip()

        logger.info("Confidence: %.2f | %s", score, reason)
        return clean, score, reason

    def _parse_verify(self, text: str) -> dict:
        """
        Extract VERDICT / ADDRESSES_BUG / NEW_ISSUES / EXPLANATION from
        a Verify response. Returns a dict; all fields default gracefully.
        """
        v = _VERDICT_RE.search(text)
        a = _ADDR_RE.search(text)
        n = _NEWISS_RE.search(text)
        e = _EXPL_RE.search(text)

        verdict      = v.group(1).upper() if v else "UNCERTAIN"
        addresses    = a.group(1).upper() if a else "NO"
        new_issues   = n.group(1).strip() if n else "Unknown"
        explanation  = e.group(1).strip() if e else "Not provided"

        if not v:
            logger.warning("VERDICT line not found in verify response; defaulting to UNCERTAIN")

        logger.info("Verify verdict: %s | Addresses bug: %s", verdict, addresses)
        return {
            "verdict":      verdict,
            "addresses_bug": addresses,
            "new_issues":   new_issues,
            "explanation":  explanation,
            "raw":          text,
        }

    # ------------------------------------------------------------------
    # RAG retrieval (public — used by app.py for progressive UI)
    # ------------------------------------------------------------------

    def retrieve(self, code: str, description: str = "") -> tuple[list[str], str]:
        """
        Retrieve top-3 knowledge base chunks for code + description.
        Returns (chunks_list, formatted_context_text).
        """
        query = f"{description} {code}"
        chunks = self.rag.retrieve(query, top_k=3)
        context_text = (
            "\n\n---\n\n".join(chunks) if chunks else "No relevant context retrieved."
        )
        logger.info("RAG retrieved %d chunks", len(chunks))
        return chunks, context_text

    # ------------------------------------------------------------------
    # Individual steps (public — called directly by app.py for step-by-step UI)
    # ------------------------------------------------------------------

    def step_plan(self, code: str, description: str, context_text: str) -> str:
        return self._call_claude(
            system=(
                "You are an expert Python debugger. Your job is to classify the type of "
                "bug present in code.\n"
                "Output 2-3 sentences: name the bug category, explain the mechanism, "
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

    def step_diagnose(
        self, code: str, description: str, context_text: str, plan: str
    ) -> str:
        """Returns raw text including CONFIDENCE/REASON lines."""
        return self._call_claude(
            system=(
                "You are an expert Python debugger performing a deep diagnosis.\n"
                "Given a preliminary bug classification, identify the exact line(s) causing "
                "the bug, explain WHY the code fails, and describe what correct behavior "
                "should look like.\n\n"
                "After your diagnosis, append exactly these two lines (no extra text after them):\n"
                "CONFIDENCE: <float from 0.0 to 1.0>\n"
                "REASON: <one sentence explaining your confidence level>"
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

    def step_fix(self, code: str, diagnosis: str) -> str:
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

    def step_verify(self, original_code: str, fixed_code: str, diagnosis: str) -> str:
        """
        Compare original vs fixed code against the diagnosis and issue a verdict.
        Returns raw text containing the four structured lines.
        """
        return self._call_claude(
            system=(
                "You are a code review expert. Compare the original code and the proposed "
                "fix against the diagnosis.\n\n"
                "Respond with EXACTLY these four labelled lines — no other text:\n"
                "VERDICT: <VERIFIED|NEEDS_REVIEW|UNCERTAIN>\n"
                "ADDRESSES_BUG: <YES|NO|PARTIAL>\n"
                "NEW_ISSUES: <NONE or a brief one-line description>\n"
                "EXPLANATION: <one to two sentences summarising your assessment>"
            ),
            user=(
                f"DIAGNOSIS:\n{diagnosis}\n\n"
                f"ORIGINAL CODE:\n```python\n{original_code}\n```\n\n"
                f"FIXED CODE:\n{fixed_code}\n\n"
                "Does the fix correctly address the diagnosed bug? "
                "Does it introduce any new issues?"
            ),
            step_name="VERIFY",
        )

    # ------------------------------------------------------------------
    # Private aliases used internally by run()
    # ------------------------------------------------------------------

    def _step_plan(self, code, description, context_text):
        return self.step_plan(code, description, context_text)

    def _step_diagnose(self, code, description, context_text, plan):
        return self.step_diagnose(code, description, context_text, plan)

    def _step_fix(self, code, diagnosis):
        return self.step_fix(code, diagnosis)

    def _step_verify(self, original_code, fixed_code, diagnosis):
        return self.step_verify(original_code, fixed_code, diagnosis)

    # ------------------------------------------------------------------
    # Public entry point (full pipeline, used by eval harness and tests)
    # ------------------------------------------------------------------

    def run(self, code: str, description: str = "") -> dict:
        """
        Run the full Plan -> Diagnose -> Fix -> Verify pipeline.

        Returns a dict with keys:
            error              — str or None
            plan               — str
            diagnosis          — str (confidence lines stripped)
            fixed_code         — str
            context            — list[str] of RAG chunks
            confidence         — float in [0.0, 1.0]
            confidence_reason  — str
            verification       — dict: {verdict, addresses_bug, new_issues,
                                        explanation, raw}
        """
        logger.info("DebuggingAgent.run() | code_len=%d | desc=%r", len(code), description)

        # Guardrail
        valid, error_msg = self._validate_input(code)
        if not valid:
            logger.warning("Guardrail rejected input: %s", error_msg)
            return {
                "error": error_msg,
                "plan": None, "diagnosis": None, "fixed_code": None,
                "context": [], "confidence": None, "confidence_reason": None,
                "verification": None,
            }

        # RAG
        context_chunks, context_text = self.retrieve(code, description)

        # Plan -> Diagnose -> Fix -> Verify
        try:
            plan          = self._step_plan(code, description, context_text)
            raw_diagnosis = self._step_diagnose(code, description, context_text, plan)
            diagnosis, confidence, confidence_reason = self._parse_confidence(raw_diagnosis)
            fixed_code    = self._step_fix(code, diagnosis)
            raw_verify    = self._step_verify(code, fixed_code, diagnosis)
            verification  = self._parse_verify(raw_verify)
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            return {
                "error": f"Claude API error: {exc}",
                "plan": None, "diagnosis": None, "fixed_code": None,
                "context": context_chunks, "confidence": None,
                "confidence_reason": None, "verification": None,
            }

        logger.info(
            "run() complete | confidence=%.2f | verdict=%s",
            confidence, verification["verdict"],
        )
        return {
            "error": None,
            "plan": plan,
            "diagnosis": diagnosis,
            "fixed_code": fixed_code,
            "context": context_chunks,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "verification": verification,
        }
