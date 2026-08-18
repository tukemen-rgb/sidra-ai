"""Query keyword repetition must not inflate retrieval evidence scores."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore

REPO = "tukemen-rgb/site"


def _document(content: str, *, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=REPO,
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime(2026, 8, 17, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


def test_repeated_query_term_does_not_multiply_bm25_score(store: DocumentStore) -> None:
    """Keyword stuffing must not turn one lexical match into stronger evidence."""

    store.add(_document("alpha retrieval policy", path="docs/retrieval.md"))
    retriever = BM25Retriever(store)

    baseline = retriever.search("alpha", repositories=[REPO], top_k=1)
    stuffed = retriever.search("alpha alpha alpha alpha", repositories=[REPO], top_k=1)

    assert len(baseline) == 1
    assert len(stuffed) == 1
    assert stuffed[0].chunk.chunk_id == baseline[0].chunk.chunk_id
    assert stuffed[0].score == pytest.approx(baseline[0].score)


def test_repeated_query_term_cannot_cross_min_score_gate(store: DocumentStore) -> None:
    """Repeating a weak term must not manufacture enough score to pass a gate."""

    store.add(_document("beta retrieval threshold", path="docs/threshold.md"))
    retriever = BM25Retriever(store)

    baseline = retriever.search("beta", repositories=[REPO], top_k=1)
    assert len(baseline) == 1
    threshold = baseline[0].score * 1.5

    assert retriever.search(
        "beta", repositories=[REPO], top_k=1, min_score=threshold
    ) == []
    assert retriever.search(
        "beta beta beta beta",
        repositories=[REPO],
        top_k=1,
        min_score=threshold,
    ) == []
