"""
Unit tests for the RAGEngine.

These tests verify that the retrieval system loads the knowledge base,
returns relevant results, and handles edge cases without crashing.
No Claude API calls are made here — RAG is a pure local operation.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rag_engine import RAGEngine


def test_rag_loads_chunks():
    """Knowledge base should load more than zero chunks."""
    engine = RAGEngine()
    assert len(engine.chunks) > 0, "RAG engine loaded no chunks — check knowledge_base/"


def test_rag_retrieves_list():
    """retrieve() always returns a list."""
    engine = RAGEngine()
    results = engine.retrieve("off by one error counter initialization")
    assert isinstance(results, list)


def test_rag_returns_relevant_content():
    """A query about type comparison should surface the type-comparison chunk."""
    engine = RAGEngine()
    results = engine.retrieve("int string type comparison bug guess secret")
    assert len(results) > 0, "Expected at least one result for a specific query"
    combined = " ".join(results).lower()
    assert any(
        keyword in combined for keyword in ("type", "str", "int", "comparison", "cast")
    ), f"Retrieved chunks don't seem relevant to type comparison: {combined[:300]}"


def test_rag_top_k_is_respected():
    """retrieve() returns at most top_k results."""
    engine = RAGEngine()
    results = engine.retrieve("bug error logic fix", top_k=2)
    assert len(results) <= 2


def test_rag_empty_query_returns_list():
    """An empty query should return an empty list without raising."""
    engine = RAGEngine()
    results = engine.retrieve("")
    assert results == []


def test_rag_missing_dir_returns_empty():
    """RAGEngine with a non-existent directory should degrade gracefully."""
    engine = RAGEngine(knowledge_dir="/nonexistent/path")
    results = engine.retrieve("anything")
    assert results == []
