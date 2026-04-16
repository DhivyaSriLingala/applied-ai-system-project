"""
Reliability Evaluation Suite — AI Bug Inspector
================================================
Runs the DebuggingAgent against four known-buggy Python snippets and measures:

  1. Keyword match   — does the plan or diagnosis mention the expected bug category?
  2. Fix compiles    — does the generated fix parse as valid Python (syntax check)?
  3. Confidence score — what self-reported certainty did Claude assign?

Usage (requires ANTHROPIC_API_KEY in your environment):
    python tests/eval_suite.py

Output:
    A per-case results table and a final summary printed to stdout.
    All Claude calls are also written to logs/YYYYMMDD.log.

This is a *live* evaluation — it calls the real API and costs tokens.
The automated reliability tests in test_reliability.py use mocks and
do not require an API key.
"""

import os
import re
import sys

# Allow running from the project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Test cases — known bugs with expected diagnostic keywords
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "TC-01",
        "bug_type": "Type Comparison",
        "code": (
            "def check_guess(guess, secret):\n"
            "    secret = str(secret)  # cast to string — bug\n"
            "    if guess == secret:\n"
            "        return 'Win'\n"
            "    elif guess > secret:\n"
            "        return 'Too High'\n"
            "    else:\n"
            "        return 'Too Low'\n"
        ),
        "description": "The game never detects a win even when the guess matches the secret.",
        "expected_keywords": ["type", "str", "int", "cast", "comparison"],
    },
    {
        "id": "TC-02",
        "bug_type": "Off-By-One Counter",
        "code": (
            "attempts = 1   # should be 0\n"
            "attempt_limit = 8\n"
            "attempts_left = attempt_limit - attempts\n"
            "print(f'You have {attempts_left} attempts remaining')\n"
        ),
        "description": "Attempts counter shows 7 remaining at game start instead of 8.",
        "expected_keywords": ["off", "one", "counter", "init", "0", "1"],
    },
    {
        "id": "TC-03",
        "bug_type": "Logic Inversion",
        "code": (
            "def get_hint(guess, secret):\n"
            "    if guess < secret:\n"
            "        return 'Go LOWER!'\n"
            "    else:\n"
            "        return 'Go HIGHER!'\n"
        ),
        "description": "Hints are backwards — guessing too low says go lower.",
        "expected_keywords": ["invert", "inversion", "swap", "logic", "backwards",
                              "lower", "higher", "wrong"],
    },
    {
        "id": "TC-04",
        "bug_type": "Hardcoded Magic Number",
        "code": (
            "import random\n\n"
            "def new_game(difficulty):\n"
            "    low, high = get_range_for_difficulty(difficulty)\n"
            "    # Bug: ignores difficulty range and always uses 1-100\n"
            "    secret = random.randint(1, 100)\n"
            "    return secret\n"
        ),
        "description": "New game always picks from 1-100 regardless of difficulty setting.",
        "expected_keywords": ["hardcoded", "magic", "range", "difficulty", "100", "low", "high"],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_python_block(text: str) -> str | None:
    """Pull the first ```python ... ``` block out of a markdown string."""
    match = re.search(r"```python\s*([\s\S]+?)```", text)
    return match.group(1).strip() if match else None


def _compiles(code: str) -> bool:
    """Return True if code parses as valid Python (syntax only, no execution)."""
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def _keywords_found(plan: str, diagnosis: str, keywords: list[str]) -> bool:
    """Return True if any expected keyword appears (case-insensitive) in plan or diagnosis."""
    haystack = (plan + " " + diagnosis).lower()
    return any(kw.lower() in haystack for kw in keywords)


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_eval() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "\n[ERROR] ANTHROPIC_API_KEY is not set.\n"
            "Export it before running:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
        )
        sys.exit(1)

    from ai_agent import DebuggingAgent

    agent = DebuggingAgent()

    print("\n" + "=" * 66)
    print("  AI Bug Inspector — Reliability Evaluation Suite")
    print("=" * 66)

    results = []

    for tc in TEST_CASES:
        print(f"\nRunning {tc['id']} | {tc['bug_type']} ...", flush=True)

        result = agent.run(tc["code"], tc["description"])

        if result["error"]:
            print(f"  ✗ Agent error: {result['error']}")
            results.append({**tc, "keyword": False, "compiles": False, "confidence": 0.0})
            continue

        keyword_ok = _keywords_found(
            result["plan"] or "",
            result["diagnosis"] or "",
            tc["expected_keywords"],
        )

        fixed_block = _extract_python_block(result["fixed_code"] or "")
        compile_ok = _compiles(fixed_block) if fixed_block else False

        conf = result.get("confidence") or 0.0
        conf_reason = result.get("confidence_reason") or "—"

        kw_icon = "✓" if keyword_ok else "✗"
        cc_icon = "✓" if compile_ok else "✗"
        print(f"  keyword match: {kw_icon}  |  fix compiles: {cc_icon}  |  confidence: {conf:.2f}")
        print(f"  confidence reason: {conf_reason}")

        results.append({
            **tc,
            "keyword": keyword_ok,
            "compiles": compile_ok,
            "confidence": conf,
            "confidence_reason": conf_reason,
        })

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    n = len(results)
    kw_pass = sum(1 for r in results if r["keyword"])
    cc_pass = sum(1 for r in results if r["compiles"])
    avg_conf = sum(r["confidence"] for r in results) / n if n else 0.0

    # Guardrail spot-check (no API call should be made for empty input)
    from unittest.mock import patch, MagicMock
    with patch("ai_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        g_agent = DebuggingAgent()
        g_result = g_agent.run("")
        guardrail_pass = (
            g_result["error"] is not None
            and mock_client.messages.create.call_count == 0
        )

    print("\n" + "=" * 66)
    print("  SUMMARY")
    print("=" * 66)
    print(f"  Cases run              : {n} / {n}")
    print(f"  Keyword match          : {kw_pass} / {n}  ({kw_pass/n:.0%})")
    print(f"  Fix compiles (syntax)  : {cc_pass} / {n}  ({cc_pass/n:.0%})")
    print(f"  Avg confidence score   : {avg_conf:.2f} / 1.00")
    print(f"  Guardrail (empty input): {'PASS — 0 API calls' if guardrail_pass else 'FAIL'}")
    print("=" * 66 + "\n")

    # Machine-readable one-liner for README / CI badge
    print(
        f"RESULT: {kw_pass}/{n} keyword matches, {cc_pass}/{n} fixes compile, "
        f"avg confidence {avg_conf:.2f}. "
        f"Guardrail {'blocked' if guardrail_pass else 'FAILED to block'} empty input."
    )


if __name__ == "__main__":
    run_eval()
