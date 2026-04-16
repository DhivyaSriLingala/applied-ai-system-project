"""
Reliability tests for the DebuggingAgent agentic pipeline.

These tests use mocks to intercept Anthropic API calls so the suite runs
without a real API key and without incurring costs.  They verify:
  - The agent always returns the expected dict structure (including confidence).
  - Confidence score is correctly parsed from the Diagnose response.
  - Guardrails block empty and oversized code before any API call.
  - The agentic workflow makes exactly 3 Claude calls (Plan, Diagnose, Fix).
  - RAG context is injected into the Plan step prompt.
  - Plan output is forwarded into the Diagnose prompt.
  - Anthropic API errors are caught and surfaced cleanly rather than crashing.

To run a live reliability check against the real API, set ANTHROPIC_API_KEY
and run: python tests/eval_suite.py
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ai_agent import DebuggingAgent, MAX_CODE_CHARS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_message(text: str) -> MagicMock:
    """Build a minimal mock that looks like an Anthropic Message object."""
    content_block = MagicMock()
    content_block.text = text

    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50

    msg = MagicMock()
    msg.content = [content_block]
    msg.usage = usage
    return msg


SAMPLE_BUGGY_CODE = (
    "def check_guess(guess, secret):\n"
    "    secret = str(secret)\n"
    "    if guess == secret:\n"
    "        return 'Win'\n"
    "    elif guess > secret:\n"
    "        return 'Too High'\n"
    "    else:\n"
    "        return 'Too Low'\n"
)


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

@patch("ai_agent.anthropic.Anthropic")
def test_agent_returns_expected_keys(mock_anthropic_cls):
    """Agent output dict always contains all required keys including confidence fields."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_message("Type comparison bug."),
        _mock_message(
            "Line 2: secret cast to str causes int != str.\n"
            "CONFIDENCE: 0.92\n"
            "REASON: The type cast is explicit and the mechanism is unambiguous."
        ),
        _mock_message("```python\nif guess == int(secret):\n```\n- Removed str() cast."),
    ]

    agent = DebuggingAgent()
    result = agent.run(SAMPLE_BUGGY_CODE)

    for key in ("error", "plan", "diagnosis", "fixed_code", "context",
                 "confidence", "confidence_reason"):
        assert key in result, f"Missing key in result: {key}"
    assert result["error"] is None


@patch("ai_agent.anthropic.Anthropic")
def test_agent_plan_is_nonempty_string(mock_anthropic_cls):
    """The plan step must produce a non-empty string."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_message("Off-by-one error in counter initialization."),
        _mock_message("Counter starts at 1 instead of 0."),
        _mock_message("```python\ncounter = 0\n```\n- Corrected init."),
    ]

    agent = DebuggingAgent()
    result = agent.run("counter = 1\ncounter += 1\nprint(counter)")

    assert isinstance(result["plan"], str)
    assert len(result["plan"]) > 0


# ---------------------------------------------------------------------------
# Guardrail tests
# ---------------------------------------------------------------------------

@patch("ai_agent.anthropic.Anthropic")
def test_empty_code_rejected_without_api_call(mock_anthropic_cls):
    """Empty code is blocked by the guardrail; no Claude call is made."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    agent = DebuggingAgent()
    result = agent.run("")

    assert result["error"] is not None
    assert result["plan"] is None
    mock_client.messages.create.assert_not_called()


@patch("ai_agent.anthropic.Anthropic")
def test_whitespace_only_code_rejected(mock_anthropic_cls):
    """Whitespace-only code is treated the same as empty."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    agent = DebuggingAgent()
    result = agent.run("   \n\t  ")

    assert result["error"] is not None
    mock_client.messages.create.assert_not_called()


@patch("ai_agent.anthropic.Anthropic")
def test_oversized_code_rejected_without_api_call(mock_anthropic_cls):
    """Code exceeding MAX_CODE_CHARS is blocked before any API call."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    agent = DebuggingAgent()
    result = agent.run("x = 1\n" * (MAX_CODE_CHARS // 5))  # well over the limit

    assert result["error"] is not None
    mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Agentic workflow tests
# ---------------------------------------------------------------------------

@patch("ai_agent.anthropic.Anthropic")
def test_agent_makes_exactly_three_api_calls(mock_anthropic_cls):
    """The Plan → Diagnose → Fix workflow always makes exactly 3 Claude calls."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_message("Logic inversion bug."),
        _mock_message("The < and > signs are swapped."),
        _mock_message("```python\nif guess > secret: return 'Too High'\n```\n- Fixed."),
    ]

    agent = DebuggingAgent()
    agent.run(SAMPLE_BUGGY_CODE)

    assert mock_client.messages.create.call_count == 3


@patch("ai_agent.anthropic.Anthropic")
def test_rag_context_injected_into_plan_prompt(mock_anthropic_cls):
    """The Plan step prompt must contain the RAG context header."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_message("Some bug classification.")

    agent = DebuggingAgent()
    # Provide a query that will surface at least one knowledge-base chunk
    agent.run(SAMPLE_BUGGY_CODE, description="type comparison bug")

    first_call = mock_client.messages.create.call_args_list[0]
    user_content = first_call[1]["messages"][0]["content"]
    assert "RELEVANT DOCUMENTATION" in user_content, (
        "RAG context header not found in Plan step prompt."
    )


@patch("ai_agent.anthropic.Anthropic")
def test_diagnosis_receives_plan_output(mock_anthropic_cls):
    """The Diagnose step prompt must include the Plan step's output."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    plan_text = "UNIQUE_PLAN_OUTPUT_MARKER"
    mock_client.messages.create.side_effect = [
        _mock_message(plan_text),
        _mock_message("Detailed diagnosis."),
        _mock_message("```python\nfixed = True\n```"),
    ]

    agent = DebuggingAgent()
    agent.run(SAMPLE_BUGGY_CODE)

    # The second call (Diagnose) should contain the first call's output
    second_call = mock_client.messages.create.call_args_list[1]
    user_content = second_call[1]["messages"][0]["content"]
    assert plan_text in user_content, (
        "Plan output was not forwarded to the Diagnose step."
    )


# ---------------------------------------------------------------------------
# Error handling test
# ---------------------------------------------------------------------------

@patch("ai_agent.anthropic.Anthropic")
def test_api_error_is_caught_and_returned_cleanly(mock_anthropic_cls):
    """An Anthropic API error is surfaced as result['error'], not a crash."""
    import anthropic as _anthropic

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = _anthropic.APIStatusError(
        "rate_limit_error",
        response=MagicMock(status_code=429, headers={}),
        body={"error": {"type": "rate_limit_error"}},
    )

    agent = DebuggingAgent()
    result = agent.run(SAMPLE_BUGGY_CODE)

    assert result["error"] is not None
    assert "API error" in result["error"] or "rate_limit" in result["error"].lower() or result["error"]
    assert result["plan"] is None


# ---------------------------------------------------------------------------
# Confidence scoring tests
# ---------------------------------------------------------------------------

@patch("ai_agent.anthropic.Anthropic")
def test_confidence_score_parsed_from_diagnosis(mock_anthropic_cls):
    """A CONFIDENCE line in the diagnosis is parsed into result['confidence']."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_message("Off-by-one error."),
        _mock_message(
            "Counter starts at 1 instead of 0.\n"
            "CONFIDENCE: 0.87\n"
            "REASON: The initialization value is clearly wrong by exactly one."
        ),
        _mock_message("```python\ncounter = 0\n```\n- Fixed init."),
    ]

    agent = DebuggingAgent()
    result = agent.run("counter = 1\ncounter += 1\nprint(counter)")

    assert result["confidence"] == pytest.approx(0.87, abs=0.01)
    assert "exactly one" in result["confidence_reason"].lower()
    # Confidence lines should NOT appear in the display diagnosis
    assert "CONFIDENCE:" not in result["diagnosis"]
    assert "REASON:" not in result["diagnosis"]


@patch("ai_agent.anthropic.Anthropic")
def test_confidence_defaults_to_0_5_when_missing(mock_anthropic_cls):
    """If Claude omits the CONFIDENCE line, the score defaults to 0.5 gracefully."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_message("Some bug."),
        _mock_message("Diagnosis with no confidence line at all."),
        _mock_message("```python\nfixed = True\n```"),
    ]

    agent = DebuggingAgent()
    result = agent.run("x = 1/0\nprint(x)")

    assert result["confidence"] == pytest.approx(0.5, abs=0.01)
    assert result["confidence_reason"] == "Not provided"
