# 💭 Reflection: Game Glitch Investigator → AI Bug Inspector

Answer each question in 3 to 5 sentences. Be specific and honest about what actually happened while you worked. This is about your process, not trying to sound perfect.

## 1. What was broken when you started?

- What did the game look like the first time you ran it?

I found it interesting. But initially, for my first game, I found it confusing. The sidebar showed "Range: 1 to 20" when I selected Easy difficulty, but the prompt under "Make a guess" told me to guess a number between 1 and 100. I did not know which range was actually correct. On top of that, the attempts counter felt off — the sidebar said 8 attempts allowed but I only saw 7 attempts left before I even guessed anything.

- List at least two concrete bugs you noticed at the start
  (for example: "the secret number kept changing" or "the hints were backwards").

**Bug 1 — Range mismatch:** The sidebar correctly showed the difficulty range (e.g. 1 to 20 for Easy), but the info message under "Make a guess" was hardcoded to always say "Guess a number between 1 and 100" regardless of difficulty. This made it impossible to know the real range.

**Bug 2 — Attempts off by one:** The "Attempts left" counter started one lower than it should have. On Normal difficulty with 8 allowed attempts, it showed 7 left before the first guess was even made. The cause was that `st.session_state.attempts` was initialized to `1` instead of `0`.

---

## 2. How did you use AI as a teammate?

- Which AI tools did you use on this project (for example: ChatGPT, Gemini, Copilot)?

I used **Claude (Claude Code / Claude Agent mode)** throughout this project — for identifying bugs, refactoring code, writing fixes, and generating tests.

- Give one example of an AI suggestion that was correct (including what the AI suggested and how you verified the result).

**Correct suggestion — refactoring logic into `logic_utils.py`:** I asked Claude in Agent mode to move `check_guess`, `parse_guess`, `get_range_for_difficulty`, and `update_score` from `app.py` into `logic_utils.py`, fix the high/low bug, and update the import in `app.py`. Claude correctly identified that the original `check_guess` was casting `secret` to a string on even attempts (causing wrong hints), moved all functions cleanly, and updated the import. I verified this by running the app and confirming that "Too High" and "Too Low" hints were now always correct, and by running `pytest` which confirmed all tests passed.

- Give one example of an AI suggestion that was incorrect or misleading (including what the AI suggested and how you verified the result).

**Misleading suggestion — changes made in a worktree instead of the original folder:** When I first asked Claude to fix the bugs, it applied all the changes inside `.claude/worktrees/exciting-sinoussi/` — a separate isolated copy of the repo — rather than in my actual project folder `ai110-module1show-gameglitchinvestigator-starter/`. The files in my main folder were untouched. I caught this by noticing the path shown in the terminal was `.claude\worktrees\exciting-sinoussi` instead of my project root. I had to explicitly tell Claude to redo the changes in the original directory, which it did correctly the second time.

---

## 3. Debugging and testing your fixes

- How did you decide whether a bug was really fixed?

For Bug 1 (range mismatch), I verified visually by switching between Easy, Normal, and Hard in the sidebar and confirming the info message updated to match the displayed range each time. For Bug 2 (attempts off by one), I checked that on a fresh game load, "Attempts left" matched the total shown in the sidebar before any guess was submitted.

- Describe at least one test you ran (manual or using pytest)
  and what it showed you about your code.

I ran `pytest tests/test_game_logic.py -v` after all fixes were applied. All 5 tests passed: the three original `check_guess` tests (which I also had to fix because they were asserting against a plain string but `check_guess` returns a tuple) and two new tests I added for Bug 2 — `test_attempts_left_at_game_start` and `test_attempts_off_by_one_regression`. The regression test explicitly demonstrated that `attempt_limit - 1` (the buggy state) does not equal `attempt_limit`, while `attempt_limit - 0` (the fixed state) does.

- Did AI help you design or understand any tests? How?

Yes. I asked Claude to generate a pytest case that specifically targeted Bug 2. Claude wrote `test_attempts_left_at_game_start` to assert that `attempt_limit - 0 == attempt_limit` (all attempts available at game start), and `test_attempts_off_by_one_regression` to explicitly show both the broken and fixed states side by side. Claude also caught that the three existing tests were broken — they called `check_guess` expecting a string return value, but the function actually returns a `(outcome, message)` tuple — and updated them to unpack correctly.

---

## 4. What did you learn about Streamlit and state?

- In your own words, explain why the secret number kept changing in the original app.

In the original app, `random.randint(low, high)` was called at the top level every time the script ran — and Streamlit reruns the entire script from top to bottom on every user interaction (button click, text input, anything). So every time I submitted a guess, a brand new secret number was generated, making it impossible to actually win. The secret was not being remembered between those reruns.

- How would you explain Streamlit "reruns" and session state to a friend who has never used Streamlit?

Imagine every time you click a button on a webpage, the entire page reloads from scratch and forgets everything — that is how Streamlit works by default. `st.session_state` is like a sticky notepad that survives those reloads: you write something on it once and it stays there even when the page reruns. So wrapping the secret number in `if "secret" not in st.session_state` means it only gets generated once, on the very first load, and stays the same for the whole game.

- What change did you make that finally gave the game a stable secret number?

The fix was guarding the secret generation with `if "secret" not in st.session_state`. This means `random.randint(low, high)` only runs the first time the app loads for a new session. On every subsequent rerun — triggered by guesses, button clicks, or sidebar changes — the condition is false and the existing secret is kept. Starting a new game explicitly resets `st.session_state.secret` to a fresh random number using the correct difficulty range.

---

## 5. Looking ahead: your developer habits

- What is one habit or strategy from this project that you want to reuse in future labs or projects?
  - This could be a testing habit, a prompting strategy, or a way you used Git.

I want to keep the habit of adding `# FIXME: Logic breaks here` comments before touching any code. It forced me to slow down, find the exact line that was wrong, and give the AI a precise target instead of a vague description. That made the AI suggestions much more accurate and saved time going back and forth.

- What is one thing you would do differently next time you work with AI on a coding task?

Next time I would verify the file paths the AI is editing before accepting any changes — this project taught me that the AI can confidently make changes in the wrong folder (the worktree) while the original files stay broken. A quick glance at the path in the terminal would have saved me an extra round of corrections.

- In one or two sentences, describe how this project changed the way you think about AI generated code.

I used to assume AI-generated code was either right or wrong in an obvious way, but this project showed me it can be subtly wrong in ways that look fine at first glance — like hints that said "Go HIGHER" when the guess was already too high, or a counter that was always off by exactly one. AI is a powerful teammate but it still needs a human to read carefully, test deliberately, and catch the quiet bugs.

---

## 6. Responsible AI Reflection (Applied AI System Project)

### What are the limitations or biases in your system?

**Lexical retrieval blindspot.** The RAG engine uses TF-IDF, which matches keywords rather than meaning. A user who describes their bug as "the hints are lying to me" will not retrieve the Logic Inversion chunk because the words don't overlap — they'd need to write "inverted comparison" or "backwards condition." This is a real usability gap: non-technical descriptions, which are exactly what beginners write, are least likely to benefit from retrieval.

**Narrow knowledge base.** The three knowledge base files cover Python game bugs, Streamlit session state, and guessing game patterns. Any code outside this domain — data science, web backends, async code — gets little RAG benefit and falls back on Claude's general training. The system appears equally confident in those cases but is reasoning without grounded context.

**No execution verification.** The Fix step produces code that passes Python's `compile()` syntax check, but it never actually *runs* the code. A generated fix can be syntactically valid and still be logically wrong — it might fix the reported bug while introducing a new one. The system presents fixes with confidence it has not earned through testing.

**Self-reported confidence is not calibrated accuracy.** The average confidence score across the four eval cases was 0.89. That is Claude's *subjective certainty*, not an empirically measured accuracy rate. Language models are known to be overconfident — the same model that claims 0.92 confidence on a correct fix might also claim 0.85 on a wrong one. Displaying this number without a disclaimer risks misleading users into trusting the output more than they should.

**Training data bias toward common patterns.** Claude was trained on a large corpus of public code and Stack Overflow answers, which overrepresents popular, well-documented bugs in widely-used frameworks. Unusual bugs in niche domains, obfuscated code, or non-English codebases are likely to receive weaker diagnoses. The system will appear most reliable to the users who need it least.

---

### Could your AI be misused, and how would you prevent that?

**Sensitive data exposure.** The most immediate risk is a user pasting code that contains secrets — API keys, database passwords, tokens embedded in a config. The current system logs the full code at DEBUG level and sends it to Anthropic's API. A developer who pastes a real production file could inadvertently exfiltrate credentials.

*Prevention:* Add a regex pre-scan for patterns like `sk-`, `-----BEGIN`, `password =`, or anything resembling a secret, and warn the user before processing. Strip matched patterns before sending. Add a visible disclaimer in the UI: "Do not paste code containing API keys, passwords, or personal data."

**Vulnerability scouting.** Asking the system to "debug" code is functionally equivalent to asking it to find exploitable flaws. An attacker could paste a target application's code and use the diagnosis to understand where the logic breaks down or where boundary conditions are wrong.

*Prevention:* This is harder to prevent because the useful and harmful use cases share the same interface. The most practical mitigation is logging and rate limiting so that systematic, high-volume use (scanning many files) is detectable and interruptible. A terms-of-service agreement and account-based access would create accountability.

**Misplaced trust in generated fixes.** If a developer deploys a Claude-generated fix without verifying it, they are betting on an LLM's judgment over their own. For security-sensitive code — authentication, input validation, cryptography — this could introduce new vulnerabilities while appearing to fix the old ones.

*Prevention:* The UI should always display the confidence score alongside a reminder: "This fix has not been executed or tested. Review it before use." The system should also avoid presenting the fix as authoritative — "Here is a possible fix" is safer framing than "Fixed code."

---

### What surprised you while testing AI reliability?

The result that surprised me most was that the confidence score was *lower* for the hardcoded magic number case (0.79) than for the logic inversion case (0.95). My intuition was that a simple number substitution bug would be easy to diagnose with high certainty. But Claude's lower confidence reflects something real: the correct fix — `random.randint(low, high)` — depends on knowing what `low` and `high` are supposed to be, which requires understanding the surrounding system. The logic inversion bug, by contrast, is self-contained and verifiable with a single trace-through. Claude was more carefully calibrated than I expected.

The second surprise was how much the three-step pipeline amplified small errors. During early testing, a vague Plan response — one that used the word "bug" without naming a category — produced a Diagnosis that was similarly vague, and then a Fix that addressed a different part of the code than was actually broken. The pipeline compounded the uncertainty rather than correcting it. This taught me that the Plan step is the most important to get right: it sets the direction for everything downstream. A bad plan does not get better with more reasoning.

---

### Describe your collaboration with AI during this project

Working with Claude throughout this project felt less like issuing commands to a tool and more like pair-programming with a fast, well-read colleague who occasionally misremembers details. Claude drafted most of the structural code — the agent pipeline, the RAG engine, the test suite — quickly and correctly on the first pass. The collaboration was genuinely productive, but it required active supervision.

**One instance where the AI gave a helpful suggestion:**

When I was designing the confidence scoring feature, my first instinct was to add a fourth Claude API call after the Fix step — a separate "self-assessment" prompt asking Claude to rate its own certainty. Claude suggested instead embedding the confidence request at the end of the Diagnose step's system prompt: instruct Claude to append `CONFIDENCE: X.X` and `REASON: ...` to the same response it was already generating, then parse those lines out. This approach adds zero latency and zero token cost beyond what the Diagnose step already spends. I verified it was cleaner by checking that the test suite still showed exactly three API calls — not four — which confirmed the pipeline structure was preserved.

**One instance where the AI's suggestion was flawed:**

When writing the test for `anthropic.APIStatusError`, Claude initially constructed the mock like this:

```python
mock_client.messages.create.side_effect = anthropic.APIStatusError("rate_limit_error")
```

This failed immediately because `APIStatusError` requires two additional keyword arguments — `response` (an HTTP response object with `status_code` and `headers`) and `body` (a dict describing the error). Claude had not checked the SDK's constructor signature and guessed at the interface. I had to look up the Anthropic Python SDK source to find the correct structure:

```python
anthropic.APIStatusError(
    "rate_limit_error",
    response=MagicMock(status_code=429, headers={}),
    body={"error": {"type": "rate_limit_error"}},
)
```

This is a common failure mode when AI generates code for third-party libraries: it knows the class exists and its general purpose, but guesses at the specifics. The fix was straightforward once I read the source, but it was a reminder that AI-generated code for library internals should always be verified against the actual documentation.
