"""
Reliability Evaluation Suite — AI Bug Inspector
================================================
Runs the DebuggingAgent against six known-buggy Python snippets and measures:

  1. Keyword match   — does plan/diagnosis mention the expected bug category?
  2. Fix compiles    — does the generated fix parse as valid Python?
  3. Confidence pass — is the self-reported confidence score > 0.70?
  4. Verify verdict  — did the Verify step agree the fix is correct?
  5. Case pass       — all four metrics must pass for a case to be PASS

Usage (requires ANTHROPIC_API_KEY):
    python tests/eval_suite.py             # human-readable summary
    python tests/eval_suite.py --json      # machine-readable JSON output

This is a LIVE evaluation — real API calls are made and tokens are spent.
The automated tests in test_reliability.py use mocks and need no API key.
"""

import argparse
import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "TC-01",
        "bug_type": "Type Comparison",
        "code": (
            "def check_guess(guess, secret):\n"
            "    secret = str(secret)  # cast to string -- bug\n"
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
        "description": "Hints are backwards -- guessing too low says go lower.",
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
    {
        "id": "TC-05",
        "bug_type": "Mutable Default Argument",
        "code": (
            "def record_guess(guess, history=[]):\n"
            "    history.append(guess)\n"
            "    return history\n\n"
            "print(record_guess(5))\n"
            "print(record_guess(10))\n"
        ),
        "description": "The guess history accumulates across calls even at the start of a new game.",
        "expected_keywords": ["mutable", "default", "argument", "list", "shared", "none"],
    },
    {
        "id": "TC-06",
        "bug_type": "Missing Return Value",
        "code": (
            "def find_winner(scores):\n"
            "    if scores:\n"
            "        best = max(scores)\n"
            "        # missing: return best\n\n"
            "winner = find_winner([10, 7, 9])\n"
            "print(f'Top score: {winner}')\n"
        ),
        "description": "Printing the winner always shows None instead of the highest score.",
        "expected_keywords": ["return", "none", "missing", "implicit", "nonetype"],
    },
]

CONFIDENCE_THRESHOLD = 0.70

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_python_block(text: str) -> str | None:
    match = re.search(r"```python\s*([\s\S]+?)```", text)
    return match.group(1).strip() if match else None


def _compiles(code: str) -> bool:
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def _keywords_found(plan: str, diagnosis: str, keywords: list[str]) -> bool:
    haystack = (plan + " " + diagnosis).lower()
    return any(kw.lower() in haystack for kw in keywords)


def _grade(keyword_rate: float, compile_rate: float, avg_conf: float) -> str:
    if keyword_rate >= 0.90 and compile_rate >= 0.90 and avg_conf >= 0.80:
        return "A"
    if keyword_rate >= 0.75 and compile_rate >= 0.75 and avg_conf >= 0.65:
        return "B"
    return "C"


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_eval(output_json: bool = False) -> None:
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

    if not output_json:
        print("\n" + "=" * 68)
        print("  AI Bug Inspector -- Reliability Evaluation Suite")
        print("=" * 68)

    results = []

    for tc in TEST_CASES:
        if not output_json:
            print(f"\nRunning {tc['id']} | {tc['bug_type']} ...", flush=True)

        result = agent.run(tc["code"], tc["description"])

        if result["error"]:
            if not output_json:
                print(f"  ERROR: {result['error']}")
            results.append({**tc, "keyword": False, "compiles": False,
                            "confidence": 0.0, "confidence_reason": "",
                            "confidence_pass": False, "verify_verdict": "ERROR",
                            "case_pass": False})
            continue

        keyword_ok = _keywords_found(
            result["plan"] or "", result["diagnosis"] or "", tc["expected_keywords"]
        )
        fixed_block = _extract_python_block(result["fixed_code"] or "")
        compile_ok  = _compiles(fixed_block) if fixed_block else False
        conf        = result.get("confidence") or 0.0
        conf_pass   = conf > CONFIDENCE_THRESHOLD
        verdict     = (result.get("verification") or {}).get("verdict", "UNCERTAIN")
        # Case passes if all four checks pass
        case_pass   = keyword_ok and compile_ok and conf_pass

        if not output_json:
            kw_s  = "PASS" if keyword_ok else "FAIL"
            cc_s  = "PASS" if compile_ok else "FAIL"
            cp_s  = "PASS" if conf_pass  else "FAIL"
            cs_s  = "PASS" if case_pass  else "FAIL"
            print(f"  keyword [{kw_s}]  compiles [{cc_s}]  "
                  f"confidence {conf:.2f} [{cp_s}]  verdict [{verdict}]")
            print(f"  CASE: {cs_s}")

        results.append({
            **tc,
            "keyword":          keyword_ok,
            "compiles":         compile_ok,
            "confidence":       conf,
            "confidence_reason": result.get("confidence_reason", ""),
            "confidence_pass":  conf_pass,
            "verify_verdict":   verdict,
            "case_pass":        case_pass,
        })

    # -----------------------------------------------------------------------
    # Guardrail spot-check
    # -----------------------------------------------------------------------
    with patch("ai_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        g_agent  = DebuggingAgent()
        g_result = g_agent.run("")
        guardrail_pass = (
            g_result["error"] is not None
            and mock_client.messages.create.call_count == 0
        )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    n           = len(results)
    kw_pass     = sum(1 for r in results if r["keyword"])
    cc_pass     = sum(1 for r in results if r["compiles"])
    cp_pass     = sum(1 for r in results if r["confidence_pass"])
    case_pass_n = sum(1 for r in results if r["case_pass"])
    avg_conf    = sum(r["confidence"] for r in results) / n if n else 0.0
    grade       = _grade(kw_pass / n, cc_pass / n, avg_conf)

    if output_json:
        out = {
            "cases": [
                {
                    "id":                r["id"],
                    "bug_type":          r["bug_type"],
                    "keyword":           r["keyword"],
                    "compiles":          r["compiles"],
                    "confidence":        round(r["confidence"], 3),
                    "confidence_pass":   r["confidence_pass"],
                    "verify_verdict":    r["verify_verdict"],
                    "case_pass":         r["case_pass"],
                }
                for r in results
            ],
            "summary": {
                "n":              n,
                "case_pass":      case_pass_n,
                "keyword_pass":   kw_pass,
                "compile_pass":   cc_pass,
                "confidence_pass": cp_pass,
                "avg_confidence": round(avg_conf, 3),
                "grade":          grade,
                "guardrail_pass": guardrail_pass,
            },
        }
        print(json.dumps(out, indent=2))
        return

    print("\n" + "=" * 68)
    print("  SUMMARY")
    print("=" * 68)
    print(f"  Cases run           : {n} / {n}")
    print(f"  Cases PASS (all 4)  : {case_pass_n} / {n}  ({case_pass_n/n:.0%})")
    print(f"  Keyword match       : {kw_pass} / {n}  ({kw_pass/n:.0%})")
    print(f"  Fix compiles        : {cc_pass} / {n}  ({cc_pass/n:.0%})")
    print(f"  Confidence > {CONFIDENCE_THRESHOLD:.0%}   : {cp_pass} / {n}  ({cp_pass/n:.0%})")
    print(f"  Avg confidence      : {avg_conf:.2f} / 1.00")
    print(f"  Guardrail (empty)   : {'PASS -- 0 API calls' if guardrail_pass else 'FAIL'}")
    print(f"  GRADE               : {grade}")
    print("=" * 68 + "\n")

    print(
        f"RESULT: {case_pass_n}/{n} cases fully passed. "
        f"Keyword {kw_pass}/{n}, compile {cc_pass}/{n}, "
        f"confidence avg {avg_conf:.2f}, grade {grade}."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Bug Inspector Evaluation Suite")
    parser.add_argument(
        "--json", dest="output_json", action="store_true",
        help="Output results as machine-readable JSON"
    )
    args = parser.parse_args()
    run_eval(output_json=args.output_json)
