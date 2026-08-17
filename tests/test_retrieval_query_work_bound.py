"""Bound distinct BM25 query work without discarding rare evidence terms."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval import search as search_module
from sidra_ai.retrieval.search import BM25Retriever, _bounded_query_terms
from sidra_ai.retrieval.store import DocumentStore


def _document(content: str, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository="tukemen-rgb/sidra-ai",
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="Proprietary",
        ),
    )


def test_query_term_selector_drops_absent_terms_and_keeps_rarest_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "_MAX_SCORING_QUERY_TERMS", 3)
    terms = ("common_a", "absent", "common_b", "common_c", "rare_tail")
    document_frequency = Counter(
        {
            "common_a": 5,
            "common_b": 4,
            "common_c": 3,
            "rare_tail": 1,
        }
    )

    selected = _bounded_query_terms(terms, document_frequency)

    assert selected == ("common_b", "common_c", "rare_tail")
    assert "absent" not in selected


def test_search_prioritizes_rare_evidence_when_query_term_budget_is_saturated(
    store: DocumentStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.add(_document("common marker", "docs/common.md"))
    store.add(_document("common rare_tail", "docs/rare.md"))
    monkeypatch.setattr(search_module, "_MAX_SCORING_QUERY_TERMS", 1)

    results = BM25Retriever(store).search("common rare_tail", top_k=2)

    assert len(results) == 1
    assert results[0].provenance.path == "docs/rare.md"
    assert "rare_tail" in results[0].content
