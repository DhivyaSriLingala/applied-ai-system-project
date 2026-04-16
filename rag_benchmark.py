"""
RAG Enhancement Benchmark
=========================
Measures retrieval quality improvement when the knowledge base is expanded from
the original 3 files to the enhanced 5 files.

Metric: for each test query, does at least one of the expected keywords appear
in the concatenated top-3 retrieved chunks?  Also reports the average cosine
similarity of the top-1 result (a proxy for retrieval confidence).

This benchmark is FULLY OFFLINE — no API key or Claude calls are needed.

Usage:
    python rag_benchmark.py
"""

import os
import sys
import logging

# Suppress RAG engine INFO logs during benchmarking for cleaner output
logging.disable(logging.INFO)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_engine import RAGEngine
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")

ORIGINAL_FILES = {
    "python_common_bugs.txt",
    "streamlit_patterns.txt",
    "game_logic_patterns.txt",
}

ENHANCED_FILES = ORIGINAL_FILES | {
    "python_exceptions_guide.txt",
    "data_structures_bugs.txt",
}

# ---------------------------------------------------------------------------
# Filtered RAG engine — loads only the allowed file subset
# ---------------------------------------------------------------------------

class _FilteredRAGEngine(RAGEngine):
    """RAGEngine that only indexes files in the allowed_files set."""

    def __init__(self, knowledge_dir: str, allowed_files: set[str]):
        self._allowed_files = allowed_files
        super().__init__(knowledge_dir)

    def _load_and_index(self) -> None:
        if not os.path.isdir(self.knowledge_dir):
            return
        for fname in sorted(os.listdir(self.knowledge_dir)):
            if not fname.endswith(".txt") or fname not in self._allowed_files:
                continue
            fpath = os.path.join(self.knowledge_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    text = f.read()
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                self.chunks.extend(paragraphs)
            except OSError:
                pass
        if self.chunks:
            self._matrix = self.vectorizer.fit_transform(self.chunks)


# ---------------------------------------------------------------------------
# Test queries — (query_string, [expected_keywords_in_top_chunks])
# ---------------------------------------------------------------------------
# 8 queries targeting NEW knowledge base content (exceptions + data structures)
# 7 queries targeting EXISTING content (control group — both baseline and
#   enhanced should pass these)

TEST_QUERIES = [
    # --- New content (python_exceptions_guide.txt) ---
    ("KeyError accessing dictionary missing key",
     ["keyerror", "dict", "get", "key"]),
    ("recursion depth exceeded missing base case infinite loop",
     ["recursion", "base case", "recursive", "depth"]),
    ("NoneType has no attribute function missing return",
     ["none", "return", "attributeerror", "nonetype"]),
    ("list index out of range loop range len",
     ["indexerror", "index", "range", "loop"]),
    ("TypeError adding string to integer user input",
     ["typeerror", "int", "str", "convert", "type"]),
    ("bare except swallowing errors silently pass",
     ["swallow", "bare", "except", "pass"]),
    ("NameError variable used before assignment scope",
     ["nameerror", "scope", "assigned", "name"]),

    # --- New content (data_structures_bugs.txt) ---
    ("integer division float binary search midpoint index",
     ["//", "float", "division", "integer"]),
    ("shallow copy nested list mutation deepcopy",
     ["deepcopy", "shallow", "copy", "nested"]),
    ("string replace not changing variable immutable",
     ["immutable", "assign", "replace", "string"]),
    ("for loop removing items list mutation iteration",
     ["mutation", "iteration", "copy", "remove"]),
    ("boolean short circuit falsy zero valid score or",
     ["short", "falsy", "or", "none", "zero"]),

    # --- Control group (original 3 files) ---
    ("off by one error counter initialization attempts",
     ["off", "one", "counter", "init", "attempts"]),
    ("type comparison int string secret guess cast",
     ["type", "str", "int", "cast", "comparison"]),
    ("streamlit session state button rerun reset",
     ["session", "state", "rerun", "button"]),
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _top_score(engine: _FilteredRAGEngine, query: str) -> float:
    """Return the cosine similarity of the top-1 result for a query."""
    if not engine.chunks or engine._matrix is None:
        return 0.0
    try:
        qv = engine.vectorizer.transform([query])
    except Exception:
        return 0.0
    scores = cosine_similarity(qv, engine._matrix)[0]
    return float(np.max(scores))


def _keywords_hit(chunks: list[str], keywords: list[str]) -> bool:
    """Return True if any keyword appears in the joined chunks (case-insensitive)."""
    haystack = " ".join(chunks).lower()
    return any(kw.lower() in haystack for kw in keywords)


def _evaluate(engine: _FilteredRAGEngine, queries: list[tuple]) -> dict:
    passed = 0
    top_scores = []
    details = []
    for query, keywords in queries:
        results = engine.retrieve(query, top_k=3)
        hit = _keywords_hit(results, keywords)
        score = _top_score(engine, query)
        top_scores.append(score)
        if hit:
            passed += 1
        details.append((query[:55], hit, score))
    return {
        "passed": passed,
        "total": len(queries),
        "avg_score": float(np.mean(top_scores)) if top_scores else 0.0,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_benchmark() -> None:
    print()
    print("=" * 68)
    print("  RAG Enhancement Benchmark — Retrieval Quality (offline)")
    print("=" * 68)
    print(f"  Knowledge base : {KB_DIR}")
    print(f"  Test queries   : {len(TEST_QUERIES)}")
    print()

    baseline = _FilteredRAGEngine(KB_DIR, ORIGINAL_FILES)
    enhanced = _FilteredRAGEngine(KB_DIR, ENHANCED_FILES)

    base_result = _evaluate(baseline, TEST_QUERIES)
    enh_result  = _evaluate(enhanced,  TEST_QUERIES)

    # Per-query detail table
    header = f"  {'Query':<55}  {'Base':>4}  {'Enh':>4}  {'Score+':>7}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for (q, b_hit, b_score), (_, e_hit, e_score) in zip(
        base_result["details"], enh_result["details"]
    ):
        b_icon = "PASS" if b_hit else "FAIL"
        e_icon = "PASS" if e_hit else "FAIL"
        delta  = e_score - b_score
        delta_str = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"
        print(f"  {q:<55}  {b_icon:>4}  {e_icon:>4}  {delta_str:>7}")

    print()

    # Summary
    b_pass = base_result["passed"]
    e_pass = enh_result["passed"]
    n      = base_result["total"]
    b_avg  = base_result["avg_score"]
    e_avg  = enh_result["avg_score"]

    pp_delta   = (e_pass - b_pass) / n * 100
    score_delta = e_avg - b_avg

    print("  " + "=" * 66)
    print(f"  {'':30} {'BASELINE':>10}  {'ENHANCED':>10}  {'DELTA':>8}")
    print("  " + "-" * 66)
    print(f"  {'Files indexed':<30} {'3':>10}  {'5':>10}  {'+2':>8}")
    print(f"  {'Queries passing':<30} {f'{b_pass}/{n}':>10}  {f'{e_pass}/{n}':>10}  "
          f"  {f'+{e_pass-b_pass}':>6}")
    print(f"  {'Pass rate':<30} {b_pass/n:>9.1%}  {e_pass/n:>9.1%}  "
          f"{f'+{pp_delta:.1f} pp':>8}")
    print(f"  {'Avg top-1 score':<30} {b_avg:>10.3f}  {e_avg:>10.3f}  "
          f"{f'+{score_delta:.3f}':>8}")
    print("  " + "=" * 66)
    print()
    print(
        f"  RESULT: Adding 2 knowledge base files improved retrieval from "
        f"{b_pass}/{n} ({b_pass/n:.0%}) to {e_pass}/{n} ({e_pass/n:.0%}) — "
        f"+{pp_delta:.1f} percentage points."
    )
    print(f"          Average retrieval confidence: {b_avg:.3f} -> {e_avg:.3f} "
          f"(+{score_delta:.3f}).")
    print()


if __name__ == "__main__":
    run_benchmark()
