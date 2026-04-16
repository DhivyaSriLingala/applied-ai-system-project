"""
Few-Shot Specialization Benchmark
===================================
Compares the Plan step output format between the zero-shot baseline
(DebuggingAgent) and the few-shot specialized variant (FewShotDebuggingAgent).

Metric: does the Plan output match the structured format:
    "<Bug Category> Bug -- <mechanism>."
measured by the regex: r"[A-Za-z ]+Bug\s+--\s+.{20,}"

Modes
------
  --demo   Run with preset responses (no API key needed). Demonstrates the
           expected format difference without spending tokens.
  (default) Requires ANTHROPIC_API_KEY. Calls the real API for both agents
            on all 4 test cases and reports actual format compliance.

Usage:
    python few_shot_benchmark.py --demo
    python few_shot_benchmark.py          # requires API key
"""

import argparse
import os
import re
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import test cases from eval_suite (avoids duplication)
from tests.eval_suite import TEST_CASES

FORMAT_PATTERN = re.compile(r"[A-Za-z ]+Bug\s+--\s+.{20,}", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Preset demo responses — illustrate the baseline vs few-shot contrast
# ---------------------------------------------------------------------------

_DEMO_STANDARD_PLANS = [
    "This code has a comparison issue. The types don't seem to match when checking if the guess is correct. The problem appears to be in the equality check.",
    "There seems to be an initialization problem with the counter. The number shown to the user is incorrect at the start.",
    "The conditional logic in get_hint appears to be returning the wrong messages. The hints are reversed.",
    "The function is using a fixed value for the range instead of using the difficulty setting. This causes incorrect behavior.",
]

_DEMO_FEW_SHOT_PLANS = [
    "Type Comparison Bug -- The secret number is cast to str on line 2 before comparison, causing int != str so the == check always returns False and the win condition is never reached. The suspicious line is `secret = str(secret)`.",
    "Off-By-One Bug -- The attempts counter is initialized to 1 instead of 0, which consumes one virtual attempt before any guess is submitted, causing the displayed remaining count to be off by one. The suspicious line is `attempts = 1`.",
    "Logic Inversion Bug -- The if/else branches return the wrong hints: when guess < secret (too low) the code returns 'Go LOWER!' instead of 'Go HIGHER!', reversing the feedback. The suspicious lines are the two return statements in the if/else block.",
    "Hardcoded Magic Number Bug -- The new_game function calls random.randint(1, 100) regardless of the selected difficulty, ignoring the low/high range returned by get_range_for_difficulty. The suspicious line is `secret = random.randint(1, 100)`.",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_compliant(plan: str) -> bool:
    return bool(FORMAT_PATTERN.search(plan))


def _make_mock_message(text: str) -> MagicMock:
    content = MagicMock()
    content.text = text
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    msg = MagicMock()
    msg.content = [content]
    msg.usage = usage
    return msg


# ---------------------------------------------------------------------------
# Demo mode — no API calls
# ---------------------------------------------------------------------------

def run_demo() -> None:
    print()
    print("=" * 68)
    print("  Few-Shot Specialization Benchmark  [DEMO MODE — no API calls]")
    print("=" * 68)
    print()
    print("  Metric: does the Plan output match")
    print(f'  pattern: r"[A-Za-z ]+Bug -- .{{20,}}"')
    print()

    results = []
    for i, tc in enumerate(TEST_CASES[:4]):
        std_plan  = _DEMO_STANDARD_PLANS[i]
        fs_plan   = _DEMO_FEW_SHOT_PLANS[i]
        std_pass  = _format_compliant(std_plan)
        fs_pass   = _format_compliant(fs_plan)

        std_icon = "PASS" if std_pass else "FAIL"
        fs_icon  = "PASS" if fs_pass  else "FAIL"

        print(f"  {tc['id']} | {tc['bug_type']}")
        print(f"    Standard  [{std_icon}]: {std_plan[:90]}...")
        print(f"    Few-Shot  [{fs_icon}]:  {fs_plan[:90]}...")
        print()
        results.append((std_pass, fs_pass))

    std_rate = sum(s for s, _ in results) / len(results)
    fs_rate  = sum(f for _, f in results) / len(results)

    _print_summary(results, std_rate, fs_rate, demo=True)


# ---------------------------------------------------------------------------
# Live mode — real API calls
# ---------------------------------------------------------------------------

def run_live() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "\n[ERROR] ANTHROPIC_API_KEY not set.\n"
            "Use --demo to run without an API key, or export ANTHROPIC_API_KEY=sk-ant-...\n"
        )
        sys.exit(1)

    from ai_agent import DebuggingAgent
    from few_shot_agent import FewShotDebuggingAgent

    std_agent = DebuggingAgent()
    fs_agent  = FewShotDebuggingAgent()

    print()
    print("=" * 68)
    print("  Few-Shot Specialization Benchmark  [LIVE MODE]")
    print("=" * 68)
    print()

    results = []
    for tc in TEST_CASES[:4]:
        print(f"  Running {tc['id']} | {tc['bug_type']} ...", flush=True)

        # Standard agent — run only Plan step to save tokens
        from rag_engine import RAGEngine
        rag = RAGEngine()
        query = f"{tc['description']} {tc['code']}"
        chunks = rag.retrieve(query, top_k=3)
        context_text = "\n\n---\n\n".join(chunks) if chunks else "No context."

        std_plan = std_agent._step_plan(tc["code"], tc["description"], context_text)
        fs_plan  = fs_agent._step_plan(tc["code"], tc["description"], context_text)

        std_pass = _format_compliant(std_plan)
        fs_pass  = _format_compliant(fs_plan)

        std_icon = "PASS" if std_pass else "FAIL"
        fs_icon  = "PASS" if fs_pass  else "FAIL"

        print(f"    Standard [{std_icon}]: {std_plan[:80]}...")
        print(f"    Few-Shot [{fs_icon}]:  {fs_plan[:80]}...")
        print()
        results.append((std_pass, fs_pass))

    std_rate = sum(s for s, _ in results) / len(results)
    fs_rate  = sum(f for _, f in results) / len(results)
    _print_summary(results, std_rate, fs_rate, demo=False)


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(results: list, std_rate: float, fs_rate: float, demo: bool) -> None:
    n = len(results)
    std_pass = sum(s for s, _ in results)
    fs_pass  = sum(f for _, f in results)
    delta_pp = (fs_rate - std_rate) * 100

    print("  " + "=" * 66)
    print("  SUMMARY")
    print("  " + "-" * 66)
    print(f"  Cases run               : {n}")
    print(f"  Standard format-compliant: {std_pass} / {n}  ({std_rate:.0%})")
    print(f"  Few-Shot format-compliant: {fs_pass} / {n}  ({fs_rate:.0%})")
    print(f"  Improvement              : +{delta_pp:.0f} percentage points")
    if demo:
        print("  (Demo mode — preset responses illustrate expected contrast)")
    print("  " + "=" * 66)
    print()
    print(
        f"  RESULT: Few-Shot agent produced structured '<Category> Bug -- ...' "
        f"format in {fs_pass}/{n} cases ({fs_rate:.0%}) vs "
        f"{std_pass}/{n} ({std_rate:.0%}) for the zero-shot baseline."
    )
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Few-Shot Specialization Benchmark")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with preset responses (no API key required)",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        run_live()
