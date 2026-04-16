# AI Bug Inspector — Applied AI System Project

An applied AI system that combines **Retrieval-Augmented Generation (RAG)** and an **agentic multi-step reasoning pipeline** to automatically diagnose and fix bugs in Python code. Built on top of a prior Streamlit game project, this system demonstrates how a real-world AI application can integrate retrieval, orchestration, logging, guardrails, and automated testing into a cohesive product.

---

## Original Project (Modules 1–3)

**[Game Glitch Investigator](https://github.com/DhivyaSriLingala/ai110-module1show-gameglitchinvestigator-starter)**

The original project was a Streamlit number-guessing game intentionally shipped with four bugs: an off-by-one error in the attempt counter, a hardcoded range that ignored the selected difficulty, backwards higher/lower hints caused by an int-vs-string comparison bug, and a "New Game" button that reset to the wrong range. The goals were to practice reading AI-generated code critically, use debugging tools (pytest, Claude inline chat, Claude Agent mode) to isolate each defect, and refactor the game logic into a testable `logic_utils.py` module. All five tests passed after the fixes were applied.

---

## What This Project Does and Why It Matters

This project evolves the game debugger concept into a general-purpose **AI-powered Python debugging assistant**. A developer pastes buggy Python code into the Streamlit UI. The system then:

1. Validates the input with guardrails before spending any API tokens.
2. Retrieves the most relevant documentation from a local knowledge base using TF-IDF retrieval (RAG).
3. Runs a **three-step agentic pipeline** — Plan → Diagnose → Fix — where each Claude API call receives the previous step's output, so reasoning compounds across steps.
4. Presents the retrieved context, the bug classification, the line-level diagnosis, and the corrected code in a structured results panel.
5. Logs every API call with latency, token counts, and full output to a date-stamped file.

**Why it matters:** Most developers spend more time debugging than writing new code. An AI tool that not only explains *what* is wrong but shows *why* the code fails and then produces a working fix — grounded in documented patterns rather than hallucinated guesses — has genuine practical value. The RAG component ensures the AI's reasoning is anchored in real debugging knowledge, not just general training data.

---

## Architecture Overview

![System Architecture Diagram](assets/system_diagram.png)

The system has five logical layers:

| Layer | Components | Role |
|---|---|---|
| **Input & UI** | `app.py`, Streamlit | Accepts code + description; renders results |
| **Guardrails** | `ai_agent.py` | Rejects empty, whitespace-only, or oversized input before any API call |
| **RAG** | `rag_engine.py`, `knowledge_base/` | TF-IDF retrieval returns top-3 relevant doc chunks, injected into every Claude prompt |
| **Agentic Pipeline** | `ai_agent.py` → Claude claude-sonnet-4-6 | Three sequential Claude calls; each step's output feeds the next |
| **Observability** | `logger_config.py`, `logs/` | Every Claude call logged with latency, token counts, and full response |

**Data flow:**
```
Human pastes code
    → Guardrail check (reject or pass)
    → RAG Engine retrieves top-3 context chunks from knowledge_base/
    → Step 1 Plan  : Claude classifies the bug type        (code + RAG context)
    → Step 2 Diagnose: Claude diagnoses the exact lines    (code + context + plan)
    → Step 3 Fix   : Claude generates corrected code       (code + diagnosis)
    → Results displayed in Streamlit UI
    → Human reviews and iterates if needed
```

**Testing layer** runs independently of the live app:
```
pytest tests/
    test_game_logic.py   →  5 regression tests (original game logic)
    test_rag.py          →  6 unit tests       (retrieval correctness, edge cases)
    test_reliability.py  →  9 reliability tests (agent pipeline with mocked API)
```

---

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone the repository

```bash
git clone https://github.com/DhivyaSriLingala/applied-ai-system-project.git
cd applied-ai-system-project
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

This installs: `streamlit`, `anthropic`, `scikit-learn`, `numpy`, `pytest`, and `altair`.

### 3. Set your API key

**macOS / Linux:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**Windows (Command Prompt):**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
```

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

### 4. Run the app

```bash
streamlit run app.py
```

Open the URL shown in your terminal (usually `http://localhost:8501`). Use the **"🔍 AI Bug Inspector"** tab for the AI features. The **"🎮 Glitchy Guesser"** tab runs the original game with no API key required.

### 5. Run the tests

```bash
pytest tests/ -v
```

All 20 tests pass without an API key (the reliability tests mock the Anthropic SDK).

---

## Sample Interactions

### Example 1 — Type Comparison Bug (the original Module 1 bug)

**Input code:**
```python
def check_guess(guess, secret):
    secret = str(secret)      # accidentally cast to string
    if guess == secret:
        return "Win"
    elif guess > secret:
        return "Too High"
    else:
        return "Too Low"
```
**Description:** *"The game never detects a win even when I type the exact number."*

**Step 1 — Plan (Claude output):**
> This is a **type comparison bug**. The `secret` variable is cast to a string on line 2 before being compared to `guess`, which is an integer. In Python 3, `int == str` always returns `False`, making a win condition impossible to reach regardless of the player's input.

**Step 2 — Diagnose (Claude output):**
> **Line 2** is the root cause: `secret = str(secret)` converts an integer (e.g., `42`) into the string `"42"`. All subsequent comparisons on lines 3–7 then compare an `int` on the left to a `str` on the right. `42 == "42"` evaluates to `False` in Python 3, so the `"Win"` branch is never reached. Additionally, `42 > "42"` raises a `TypeError` in Python 3 — the higher/lower hints would crash rather than give wrong feedback. The fix is to remove the type conversion and ensure both sides of every comparison are the same type.

**Step 3 — Fix (Claude output):**
```python
def check_guess(guess, secret):
    guess = int(guess)
    secret = int(secret)
    if guess == secret:
        return "Win"
    elif guess > secret:
        return "Too High"
    else:
        return "Too Low"
```
*Changes: Removed `str(secret)` cast; added explicit `int()` casts on both sides to prevent type mismatches regardless of how the values are passed in.*

---

### Example 2 — Off-by-One Counter Bug

**Input code:**
```python
import streamlit as st

if "attempts" not in st.session_state:
    st.session_state.attempts = 1       # bug: should start at 0

attempt_limit = 8
st.info(f"Attempts left: {attempt_limit - st.session_state.attempts}")
```
**Description:** *"The attempts counter shows 7 remaining at the start of the game instead of 8."*

**Step 1 — Plan:**
> This is a classic **off-by-one error** in counter initialization. The `attempts` session state variable is initialized to `1` instead of `0`, which immediately consumes one virtual attempt before the player has made any guesses.

**Step 2 — Diagnose:**
> **Line 4**: `st.session_state.attempts = 1` sets the counter one step ahead of where it should be. When the display formula `attempt_limit - st.session_state.attempts` is evaluated on line 7, it computes `8 - 1 = 7` on the very first render — before any guess has been submitted. The player sees 7 remaining attempts even though they have used none. The fix is to initialize to `0` so the first render correctly shows `8 - 0 = 8`.

**Step 3 — Fix:**
```python
import streamlit as st

if "attempts" not in st.session_state:
    st.session_state.attempts = 0       # fixed: initialize to 0

attempt_limit = 8
st.info(f"Attempts left: {attempt_limit - st.session_state.attempts}")
```
*Changes: Changed initialization value from `1` to `0`.*

---

### Example 3 — Logic Inversion Bug

**Input code:**
```python
def get_hint(guess, secret):
    if guess < secret:
        return "Go LOWER!"
    else:
        return "Go HIGHER!"
```
**Description:** *"The hints are always backwards — when I guess too low it says go lower."*

**Step 1 — Plan:**
> This is a **logic inversion bug**. The comparison operators are swapped: the function returns `"Go LOWER!"` when `guess < secret` (i.e., the guess is actually too low and the player should go *higher*), and vice versa.

**Step 2 — Diagnose:**
> **Lines 2–3**: When `guess < secret` — for example `guess=30, secret=50` — the player's number is below the target. They need to guess *higher*, but the function returns `"Go LOWER!"`. The conditional branches are inverted. This likely originated from a copy-paste error or a misread of the comparison direction.

**Step 3 — Fix:**
```python
def get_hint(guess, secret):
    if guess < secret:
        return "Go HIGHER!"    # guess is below target → go higher
    else:
        return "Go LOWER!"     # guess is above target → go lower
```
*Changes: Swapped the return strings to match the correct logical direction. Added inline comments to make the intent explicit.*

---

## Design Decisions

### Why RAG instead of a single large prompt?

A single prompt asking Claude to "fix this code" produces reasonable results but gives the model no domain anchor — it draws purely from general training. By retrieving specific documentation chunks (e.g., the Streamlit session-state pattern, or the type-comparison bug entry) and injecting them into every step, the AI's reasoning is grounded in curated, project-specific knowledge. This also means the knowledge base can be extended without retraining any model.

**Trade-off:** TF-IDF retrieval is lexically based — it matches keywords, not semantics. A query about "the secret number resetting" might not surface the Streamlit session-state chunk if the exact words don't overlap. A semantic embedding model (e.g., `sentence-transformers`) would improve recall but adds a larger dependency and slower startup. TF-IDF was chosen to keep setup frictionless for a portfolio project.

### Why three separate Claude calls instead of one?

A single prompt asking Claude to plan, diagnose, and fix in one go produces a less structured output that is harder to surface cleanly in the UI. Separating the steps enforces a reasoning chain: the diagnosis step literally receives the plan text as part of its prompt, so it cannot skip to conclusions without first classifying the bug. The fix step receives the diagnosis, so it produces targeted corrections rather than rewriting code from scratch.

**Trade-off:** Three calls means ~3× the latency and token cost of a single call. For a production system this could be optimized with streaming or a single multi-turn conversation. For a portfolio project demonstrating agentic design, the explicitness is worth more than the efficiency.

### Why TF-IDF over a vector database?

Setting up Pinecone, Chroma, or FAISS adds infrastructure complexity that distracts from the core AI concepts. `scikit-learn`'s `TfidfVectorizer` is a standard library that requires no additional services, stores entirely in memory, and rebuilds in milliseconds from the three text files. The knowledge base is small enough (< 100 paragraphs) that TF-IDF is fully adequate.

### Why mock the Anthropic API in reliability tests?

Running real API calls in a test suite creates flakiness (network failures, rate limits), costs money per run, and makes CI non-deterministic because LLM outputs vary. Mocking lets the tests verify the *structure* of the agentic workflow — that exactly 3 calls are made, that guardrails fire before any call, that the Plan output is forwarded to Diagnose, and that API errors are caught cleanly — without any of those downsides.

---

## Testing Summary

### What was tested

| Test file | Count | What it verifies |
|---|---|---|
| `test_game_logic.py` | 5 | Original game: win/lose/hint correctness, off-by-one regression |
| `test_rag.py` | 6 | Knowledge base loads, retrieval returns relevant chunks, edge cases (empty query, bad directory) |
| `test_reliability.py` | 9 | Agent returns correct dict structure, guardrails block invalid input before API call, exactly 3 Claude calls made, RAG context present in Plan prompt, Plan output forwarded to Diagnose, API errors caught cleanly |

**Result: 20/20 tests pass.**

### What worked well

- Mocking the Anthropic client with `unittest.mock.patch` was straightforward and made the reliability tests fully deterministic.
- The guardrail tests gave immediate confidence that oversized or empty inputs would never reach the API — a real cost and safety control.
- The `test_diagnosis_receives_plan_output` test (checking that a unique string from Step 1 appears in the Step 2 prompt) is particularly valuable: it proves the agentic chain is wired correctly, not just that individual calls run.

### What was harder than expected

- Mocking `anthropic.APIStatusError` required inspecting the SDK source to understand its constructor signature (`response`, `body` parameters). The error-handling test needed a few iterations to use the right arguments.
- TF-IDF retrieval requires enough keyword overlap between query and chunk to score above the relevance threshold. Some natural-language descriptions of bugs ("the hints lie to me") don't surface the right chunks without also including technical keywords. The UI prompts users to include a technical description for this reason.

### What I learned

Testing AI systems requires a different mental model than testing deterministic functions. The goal is not "does it return the right answer" (which varies by model and temperature) but rather "does it follow the right *process*" — correct number of steps, correct data passed between steps, correct guardrail behavior. Designing tests around process rather than output made the suite far more stable and meaningful.

---

## Reflection

### What this project taught me about AI systems

Building a retrieval-augmented agentic system made concrete something that is easy to miss when just calling an API: **the quality of an AI output is largely determined before the model ever sees the prompt**. The retrieval step, the guardrails, the way previous step outputs are formatted and forwarded — these structural decisions shape the final answer more than model temperature or prompt wording.

The agentic pattern also showed the value of decomposition. A single "diagnose and fix this bug" prompt produces a serviceable answer. Breaking it into Plan → Diagnose → Fix — where each step's output becomes the next step's grounding context — produces more precise, more explainable results. This mirrors how a careful human developer approaches debugging: categorize first, then investigate the specific mechanism, then write the fix.

### What I would do differently

- **Semantic retrieval:** Replace TF-IDF with `sentence-transformers` embeddings. Natural-language bug descriptions would match relevant chunks far more reliably, even without technical keyword overlap.
- **Streaming responses:** Display Claude's output token-by-token using the Anthropic streaming API so the user sees progress during the ~5-second pipeline rather than waiting for a spinner.
- **Evaluation harness:** Build a small labeled dataset of buggy code snippets with known correct fixes, then measure the Fix step's accuracy automatically. This would turn the reliability tests from structural checks into outcome checks.
- **Memory across sessions:** Log each debugging session's inputs and outputs, then use that history to fine-tune retrieval — surfacing chunks that were most useful for similar past bugs.

### Final thought

This project changed how I read AI-generated code. Every time the AI produces a fix, I now ask: *what context did it retrieve, what did it classify, what mechanism did it identify?* That question — tracing the reasoning chain rather than just accepting the answer — is the core skill this work taught me.

---

## Project Structure

```
applied-ai-system-project/
├── app.py                          # Streamlit UI (game tab + AI Bug Inspector tab)
├── ai_agent.py                     # DebuggingAgent: Plan → Diagnose → Fix pipeline
├── rag_engine.py                   # TF-IDF retrieval over knowledge_base/
├── logic_utils.py                  # Original game logic (unchanged from Module 1)
├── logger_config.py                # Centralized logging to console + logs/
├── requirements.txt
├── knowledge_base/
│   ├── python_common_bugs.txt      # Off-by-one, type comparison, logic inversion, etc.
│   ├── streamlit_patterns.txt      # Session state, reruns, widget keys
│   └── game_logic_patterns.txt     # Binary search, state machines, score formulas
├── assets/
│   ├── system_diagram.png          # Architecture diagram (rendered from .mmd)
│   └── system_diagram.mmd          # Mermaid source for the diagram
├── logs/                           # Date-stamped log files (auto-created at runtime)
├── tests/
│   ├── test_game_logic.py          # 5 tests — original game regression
│   ├── test_rag.py                 # 6 tests — retrieval engine
│   └── test_reliability.py         # 9 tests — agent pipeline (mocked API)
└── docs/
    ├── demo_win.png
    └── pytest_results.png
```

---

*Built with Claude claude-sonnet-4-6 (Anthropic), Streamlit, scikit-learn, and pytest.*
