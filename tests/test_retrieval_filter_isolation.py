"""Filtered retrieval must not inherit corpus statistics from excluded DATA."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore

TARGET_REPO = "tukemen-rgb/site"
NOISE_REPO = "tukemen-rgb/creater-yard"


def _document(
    content: str,
    *,
    repository: str,
    path: str,
    source_type: SourceType = SourceType.DOCS,
) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=repository,
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source_type=source_type,
            trust_level=(
                TrustLevel.EXTERNAL
                if source_type in {SourceType.ISSUE, SourceType.PULL_REQUEST}
                else TrustLevel.INTERNAL_REPO
            ),
            license="MIT",
        ),
    )


def test_repository_filter_score_is_invariant_to_unrelated_repository_growth(
    store: DocumentStore,
) -> None:
    """Adding excluded repositories must not change a scoped query's score."""

    store.add(
        _document(
            "alpha alpha retrieval policy",
            repository=TARGET_REPO,
            path="docs/target.md",
        )
    )
    retriever = BM25Retriever(store)
    before = retriever.search("alpha", repositories=[TARGET_REPO], top_k=1)
    assert len(before) == 1

    for index in range(12):
        store.add(
            _document(
                "alpha unrelated external corpus noise",
                repository=NOISE_REPO,
                path=f"docs/noise-{index}.md",
            )
        )

    after = retriever.search("alpha", repositories=[TARGET_REPO], top_k=1)
    assert len(after) == 1
    assert after[0].provenance.repository == TARGET_REPO
    assert after[0].score == pytest.approx(before[0].score)


def test_source_type_filter_score_is_invariant_to_excluded_source_growth(
    store: DocumentStore,
) -> None:
    """External issue volume must not change DOCS-only BM25 statistics."""

    store.add(
        _document(
            "beta beta architecture contract",
            repository=TARGET_REPO,
            path="docs/architecture.md",
            source_type=SourceType.DOCS,
        )
    )
    retriever = BM25Retriever(store)
    before = retriever.search(
        "beta", source_types=[SourceType.DOCS], repositories=[TARGET_REPO], top_k=1
    )
    assert len(before) == 1

    for index in range(12):
        store.add(
            _document(
                "beta issue discussion noise",
                repository=TARGET_REPO,
                path=f"issue/{100 + index}",
                source_type=SourceType.ISSUE,
            )
        )

    after = retriever.search(
        "beta", source_types=[SourceType.DOCS], repositories=[TARGET_REPO], top_k=1
    )
    assert len(after) == 1
    assert after[0].provenance.source_type is SourceType.DOCS
    assert after[0].score == pytest.approx(before[0].score)
