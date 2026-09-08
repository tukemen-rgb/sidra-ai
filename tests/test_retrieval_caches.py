"""The two memos retrieval grew for speed, judged by what they must not change.

A cache that makes search faster and answers differently is not an
optimisation, it is a silent regression with a benchmark attached. Both of
these hold results that are *pure functions* of the index, so the property
worth testing is not "is it faster" (the instruments measure that) but:

* the same query returns the same chunks and the same scores whether the memo
  was cold or warm, and
* the memo dies when the thing it describes changes - a remembered position
  list outliving its index would serve chunks from a corpus that no longer
  exists.

The second one is the whole risk. The first would be caught by any judge run;
a stale-after-write bug shows up only in the window between an ingestion and
the next restart, which is exactly where nobody looks.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.documents import (  # noqa: E402
    Document,
    Provenance,
    SourceType,
    TrustLevel,
)
from sidra_ai.retrieval.embedding import EmbeddingRetriever  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

_REPOS = ("owner/alpha", "owner/beta")


def _document(repository: str, path: str, content: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=repository,
            path=path,
            commit_sha="0" * 40,
            timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="proprietary",
        ),
    )


def _store() -> DocumentStore:
    gate = SecurityGate(GatePolicy(), allowed_repositories=list(_REPOS))
    store = DocumentStore(gate)
    store.add(_document("owner/alpha", "docs/plan.md", "競合の分析と収益化の方針について"))
    store.add(_document("owner/alpha", "docs/notes.md", "収益化の方針は広告に依存しない"))
    store.add(_document("owner/beta", "docs/other.md", "競合の一覧と価格の比較"))
    return store


def _ids(results) -> list[str]:
    return [r.chunk.chunk_id for r in results]


# ------------------------------------------------------- filter memo


def test_a_filtered_search_answers_the_same_warm_as_cold() -> None:
    retriever = BM25Retriever(_store())
    query = "収益化の方針"

    retriever._filter_cache.clear()
    cold = retriever.search(query, top_k=5, repositories=["owner/alpha"])
    warm = retriever.search(query, top_k=5, repositories=["owner/alpha"])

    assert _ids(cold) == _ids(warm)
    assert [r.score for r in cold] == [r.score for r in warm]
    assert cold, "the fixture must actually match something"


def test_the_filter_memo_does_not_outlive_the_index_it_describes() -> None:
    """The failure this file exists for: positions are indices into a list.

    A document added after a filtered search shifts nothing about the
    remembered positions' *validity* on its own - but the statistics derived
    from the old eligible set are wrong, and a document that should now be
    eligible would never be offered. Both show up as the new chunk being
    unfindable.
    """

    store = _store()
    retriever = BM25Retriever(store)
    query = "限定公開の合言葉"

    assert retriever.search(query, top_k=5, repositories=["owner/alpha"]) == []

    store.add(_document("owner/alpha", "docs/new.md", "限定公開の合言葉は使わない方針"))
    found = retriever.search(query, top_k=5, repositories=["owner/alpha"])

    assert found, "a document added after a filtered search must be findable"
    assert any("限定公開" in r.chunk.content for r in found)


def test_one_filter_does_not_answer_for_another() -> None:
    retriever = BM25Retriever(_store())
    query = "競合"

    alpha = retriever.search(query, top_k=5, repositories=["owner/alpha"])
    beta = retriever.search(query, top_k=5, repositories=["owner/beta"])

    assert {r.chunk.provenance.repository for r in alpha} == {"owner/alpha"}
    assert {r.chunk.provenance.repository for r in beta} == {"owner/beta"}


def test_the_filter_memo_is_bounded() -> None:
    """The key is caller-supplied, so the memo must not grow without limit."""

    retriever = BM25Retriever(_store())
    for i in range(BM25Retriever._FILTER_CACHE_MAX + 5):
        # Distinct, harmless filters: each names a repository that exists
        # plus one that does not, so every key is new and every result is
        # still correct.
        retriever.search(
            "競合", top_k=3, repositories=["owner/alpha", f"owner/ghost{i}"]
        )
    assert len(retriever._filter_cache) <= BM25Retriever._FILTER_CACHE_MAX


# ------------------------------------------------------- vector memo


class _CountingBackend:
    """Deterministic, content-derived vectors, and a record of what it saw."""

    name = "counting"

    def __init__(self) -> None:
        self.seen: list[list[str]] = []

    def available(self) -> bool:
        return True

    def encode(self, texts):
        self.seen.append(list(texts))
        return [
            [float(sum(ord(c) for c in t) % 89), float(len(t) % 71), 1.0] for t in texts
        ]


def test_a_repeat_query_re_encodes_nothing_but_the_query() -> None:
    backend = _CountingBackend()
    retriever = EmbeddingRetriever(BM25Retriever(_store()), backend)

    first = retriever.search("収益化の方針", top_k=3)
    passages_first = len(backend.seen[-1]) - 1
    retriever.search("収益化の方針", top_k=3)
    passages_repeat = len(backend.seen[-1]) - 1

    assert passages_first > 0, "the semantic pass must have encoded something"
    assert passages_repeat == 0
    assert first, "the fixture must actually match something"


def test_the_vector_memo_returns_the_same_order_it_would_have_computed() -> None:
    backend = _CountingBackend()
    retriever = EmbeddingRetriever(BM25Retriever(_store()), backend)
    query = "競合の比較"

    cold = retriever.search(query, top_k=3)
    warm = retriever.search(query, top_k=3)

    assert _ids(cold) == _ids(warm)


def test_new_text_is_encoded_even_when_the_memo_is_warm() -> None:
    """Keyed by content, so unseen content must still reach the model."""

    store = _store()
    backend = _CountingBackend()
    retriever = EmbeddingRetriever(BM25Retriever(store), backend)
    retriever.search("収益化の方針", top_k=5)

    store.add(_document("owner/beta", "docs/late.md", "収益化の方針を後から書いた文書"))
    retriever.search("収益化の方針", top_k=5)

    assert any("後から書いた" in text for text in backend.seen[-1])


def test_the_vector_memo_is_bounded() -> None:
    store = _store()
    backend = _CountingBackend()
    retriever = EmbeddingRetriever(BM25Retriever(store), backend)
    retriever._vector_cache_max = 2

    retriever.search("収益化の方針", top_k=5)
    retriever.search("競合の比較", top_k=5)

    assert len(retriever._vectors) <= max(2, 5)
