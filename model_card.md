# Model Card — AI Bug Inspector

**Project:** AI Bug Inspector (Applied AI System Project)
**Author:** Dhivya Sri Lingala
**Base Model:** Claude claude-sonnet-4-6 (Anthropic) / Gemini 2.0 Flash (Google)
**Last Updated:** April 2026

---

## Model Overview

The AI Bug Inspector is a RAG-augmented agentic debugging system. It accepts buggy Python code, retrieves relevant documentation from a local knowledge base using TF-IDF, and runs a four-step pipeline — Plan, Diagnose, Fix, Verify — where each step's output feeds into the next. The system is not a fine-tuned model; it uses prompt engineering, retrieval augmentation, and few-shot examples to guide a general-purpose LLM toward structured, reliable debugging outputs.

---

## AI Collaboration Reflection

### How I Used AI During This Project

I used **Claude (Claude Code / Claude Agent mode)** throughout — for identifying bugs, refactoring code, writing the agentic pipeline, designing the RAG engine, and generating tests.

**One instance where the AI gave a helpful suggestion:**

When designing confidence scoring, my first instinct was to add a fourth Claude API call — a separate "self-assessment" prompt. Claude suggested embedding the confidence request at the end of the Diagnose step's system prompt instead: instruct Claude to append `CONFIDENCE: X.X` and `REASON: ...` to the same response, then parse those lines out. This added zero latency and zero extra token cost. I verified it was correct by checking that the test suite still showed exactly four API calls (Plan, Diagnose, Fix, Verify) — not five.

**One instance where the AI's suggestion was flawed:**

When writing the test for `anthropic.APIStatusError`, Claude initially generated:
```python
mock_client.messages.create.side_effect = anthropic.APIStatusError("rate_limit_error")
```
This failed because `APIStatusError` requires two additional keyword arguments — `response` (with `status_code` and `headers`) and `body`. Claude guessed at the interface without checking the SDK's constructor signature. I had to look up the Anthropic Python SDK source to fix it:
```python
anthropic.APIStatusError(
    "rate_limit_error",
    response=MagicMock(status_code=429, headers={}),
    body={"error": {"type": "rate_limit_error"}},
)
```
This is a common AI failure mode for third-party library internals: it knows the class exists but guesses at specifics. Always verify AI-generated library code against actual documentation.

---

## Limitations and Biases

**Lexical retrieval blindspot.** The RAG engine uses TF-IDF, which matches keywords rather than meaning. A user who describes their bug as "the hints are lying to me" will not retrieve the Logic Inversion chunk — the words don't overlap. Non-technical descriptions, which beginners are most likely to write, benefit least from retrieval.

**Narrow knowledge base.** The five knowledge base files cover Python game bugs, Streamlit patterns, game logic, exceptions, and data structures. Code outside this domain — data science, async, web backends — gets little RAG benefit and falls back on general LLM training. The system appears equally confident regardless.

**No execution verification.** The Fix step produces code that passes Python's `compile()` syntax check but is never actually run. A generated fix can be syntactically valid and still logically wrong.

**Self-reported confidence is not calibrated accuracy.** The average confidence score across eval cases was 0.89. That is Claude's subjective certainty, not empirically measured accuracy. LLMs are known to be overconfident. Displaying this number without a disclaimer risks misleading users.

**Training data bias.** Claude was trained on public code that overrepresents popular, well-documented bugs in widely-used frameworks. Unusual bugs in niche domains or non-English codebases will receive weaker diagnoses.

---

## Potential Misuse and Prevention

**Sensitive data exposure.** A user pasting production code containing API keys, passwords, or tokens could inadvertently exfiltrate credentials through the API call and debug logs.
*Prevention:* Add a regex pre-scan for secret patterns (`sk-`, `-----BEGIN`, `password =`) and warn the user before processing. Display a persistent disclaimer: "Do not paste code containing API keys, passwords, or personal data."

**Vulnerability scouting.** Asking the system to "debug" code is functionally equivalent to asking it to find exploitable flaws. An attacker could use the diagnosis to understand where logic breaks down.
*Prevention:* Rate limiting and logging make systematic high-volume scanning detectable. Account-based access creates accountability.

**Misplaced trust in generated fixes.** Developers who deploy AI-generated fixes without review risk introducing new vulnerabilities.
*Prevention:* The UI always shows a confidence score alongside a reminder: "This fix has not been executed or tested. Review it before use."

---

## Testing Results

| Test Layer | Count | Result |
|---|---|---|
| Game logic regression (`test_game_logic.py`) | 5 | All pass |
| RAG retrieval unit tests (`test_rag.py`) | 6 | All pass |
| Agent reliability — mocked API (`test_reliability.py`) | 14 | All pass |
| **Total** | **25** | **25/25** |

**RAG Benchmark (offline, no API):**
- 3-file knowledge base: 8/15 queries matched (53%)
- 5-file knowledge base: 15/15 queries matched (100%)
- Improvement: +47 percentage points

**Few-Shot Benchmark (demo mode, no API):**
- Standard (zero-shot): 0/4 format compliant (0%)
- Few-shot (3 examples): 4/4 format compliant (100%)
- Improvement: +100 percentage points

---

## What Surprised Me During Testing

The confidence score was *lower* for the hardcoded magic number case (0.79) than for the logic inversion case (0.95). My intuition was that a simple number substitution would be easy to diagnose with high certainty. But the correct fix depends on knowing what `low` and `high` should be — which requires understanding the surrounding system. The logic inversion bug is self-contained and verifiable with a single trace-through. Claude was more carefully calibrated than I expected.

The second surprise was how much the four-step pipeline amplified small errors. A vague Plan response produced a vague Diagnosis, and then a Fix that addressed a different part of the code than was actually broken. This confirmed that the Plan step is the most critical: it sets the direction for everything downstream, and a bad plan does not get better with more reasoning.

---

## Intended Use

- Educational tool for Python learners debugging common mistakes
- Developer aid for quickly understanding unfamiliar bug patterns
- Demonstration of RAG + agentic pipeline design

## Out-of-Scope Use

- Production code review without human oversight
- Security-sensitive code (authentication, cryptography, input validation)
- Code containing credentials or personal data
