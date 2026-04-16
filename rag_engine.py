"""
RAG (Retrieval-Augmented Generation) engine.

Loads plain-text knowledge base files, splits them into paragraph-level chunks,
indexes them with TF-IDF, and returns the top-k most relevant chunks for a query.
The retrieved chunks are injected into Claude prompts so the AI reasons over
domain-specific documentation rather than relying on general training alone.
"""

import os
import logging

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("ai_bug_inspector.rag")

DEFAULT_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge_base")


class RAGEngine:
    """TF-IDF–based retrieval engine over a local knowledge base."""

    def __init__(self, knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR):
        self.knowledge_dir = knowledge_dir
        self.chunks: list[str] = []
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = None
        self._load_and_index()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_and_index(self) -> None:
        """Load all .txt files and build the TF-IDF index."""
        if not os.path.isdir(self.knowledge_dir):
            logger.warning(
                "Knowledge base directory not found: %s — RAG will return no context.",
                self.knowledge_dir,
            )
            return

        for fname in sorted(os.listdir(self.knowledge_dir)):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(self.knowledge_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    text = f.read()
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                self.chunks.extend(paragraphs)
                logger.debug("Loaded %d chunks from %s", len(paragraphs), fname)
            except OSError as exc:
                logger.error("Could not read %s: %s", fpath, exc)

        if self.chunks:
            self._matrix = self.vectorizer.fit_transform(self.chunks)
            logger.info("RAG index built: %d chunks total", len(self.chunks))
        else:
            logger.warning("No chunks loaded — knowledge base may be empty.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """
        Return the top-k knowledge base chunks most relevant to *query*.

        Returns an empty list if the index is empty or the query is blank.
        Only chunks with cosine similarity > 0.05 are returned.
        """
        if not self.chunks or self._matrix is None:
            return []

        if not query or not query.strip():
            return []

        try:
            query_vec = self.vectorizer.transform([query])
        except Exception as exc:
            logger.error("TF-IDF transform failed: %s", exc)
            return []

        scores = cosine_similarity(query_vec, self._matrix)[0]
        # Filter out near-zero matches before sorting
        ranked = np.argsort(scores)[::-1]
        results = [
            self.chunks[i]
            for i in ranked[:top_k]
            if scores[i] > 0.05
        ]
        logger.debug(
            "retrieve(top_k=%d) → %d results | top score=%.3f",
            top_k,
            len(results),
            float(scores[ranked[0]]) if len(ranked) else 0.0,
        )
        return results
