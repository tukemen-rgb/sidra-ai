"""Growing the index must give the same index as building it in one shot.

Ingestion appends. Serving reads. Before this, the two cost each other: any
document added to a live store made the next query re-tokenize every chunk in
it, so ingesting and answering at the same time turned into accumulated
O(N^2) - measured at 1.5 ms for a query after the first document and 1,659 ms
after the two hundred and fourth.

Reading only the new tail is obviously faster and not obviously *equal*, and
equality is the only thing worth testing here. An index that drifts as it
grows would answer differently depending on the order documents happened to
arrive in, which is the kind of defect that never reproduces on a rebuild.

The three ways it could drift, each pinned below: the postings could go out
of step with the chunks (wrong scores), the candidate index's row numbers
could stop matching the retriever's positions (right scores on the wrong
chunks), and a store that did something other than append could be mistaken
for one that did (an index describing a corpus that no longer exists).
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
from sidra_ai.retrieval.candidates import Fts5CandidateSource, fts5_available  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

_REPOS = ("owner/alpha", "owner/beta")

_TEXTS = [
    "競合の分析と収益化の方針について書いた計画の文書",
    "収益化の方針は広告に依存しない。掲載順は売らない",
    "競合の一覧と価格の比較、そして審査の基準について",
    "投稿された作品の審査は人の目で行い、結果を必ず返す",
    "個人情報は公開の保管場所へ置かない。連絡先も同じ",
    "ゲームのアップロード上限と対応形式についての決まり",
    "スレッドは使えない。単一の実行で完結させること",
    "北極星指標は月間の投稿作品数であると決めた",
]

_QUERIES = [
    "競合はどこですか",
    "収益化の方針",
    "審査の基準",
    "個人情報の扱い",
    "アップロードの上限",
    "北極星指標",
]


def _document(index: int) -> Document:
    return Document(
        content=_TEXTS[index % len(_TEXTS)] + f"（第 {index} 節）",
        provenance=Provenance(
            source="github",
            repository=_REPOS[index % len(_REPOS)],
            path=f"docs/part{index}.md",
            commit_sha="0" * 40,
            timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="proprietary",
        ),
    )


def _store() -> DocumentStore:
    gate = SecurityGate(GatePolicy(), allowed_repositories=list(_REPOS))
    return DocumentStore(gate)


def _retriever(store: DocumentStore) -> BM25Retriever:
    source = Fts5CandidateSource() if fts5_available() else None
    return BM25Retriever(store, candidate_source=source)


def _one_shot(count: int) -> BM25Retriever:
    store = _store()
    for i in range(count):
        store.add(_document(i))
    retriever = _retriever(store)
    retriever._ensure_index()
    return retriever


def _grown(count: int) -> BM25Retriever:
    store = _store()
    retriever = _retriever(store)
    for i in range(count):
        store.add(_document(i))
        # Index between every add: this is the serving-while-ingesting shape,
        # and the one where an incremental path can drift.
        retriever._ensure_index()
    return retriever


def _answers(retriever: BM25Retriever, **kwargs) -> list[tuple[str, float]]:
    return [
        (r.chunk.chunk_id, round(r.score, 10))
        for query in _QUERIES
        for r in retriever.search(query, top_k=5, **kwargs)
    ]


def test_the_postings_are_the_same_as_a_single_shot_build() -> None:
    one, grown = _one_shot(24), _grown(24)

    assert one._lengths == grown._lengths
    assert one._document_frequency == grown._document_frequency
    assert one._term_frequencies == grown._term_frequencies
    assert one._average_length == grown._average_length


def test_it_answers_the_same_as_a_single_shot_build() -> None:
    one, grown = _one_shot(24), _grown(24)

    assert _answers(one) == _answers(grown)
    assert _answers(one), "the fixture must actually match something"


def test_it_answers_the_same_under_a_repository_filter() -> None:
    """Filtered search reads positions and per-filter statistics; both move
    when the index grows, and neither may end up describing the old corpus."""

    one, grown = _one_shot(24), _grown(24)

    for repository in _REPOS:
        assert _answers(one, repositories=[repository]) == _answers(
            grown, repositories=[repository]
        )


def test_a_document_added_after_a_query_is_findable_immediately() -> None:
    store = _store()
    retriever = _retriever(store)
    for i in range(6):
        store.add(_document(i))
    retriever.search("競合はどこですか", top_k=5)

    store.add(
        Document(
            content="真夜中の合言葉についての決まりを書いた節",
            provenance=_document(0).provenance.__class__(
                source="github",
                repository="owner/alpha",
                path="docs/late.md",
                commit_sha="0" * 40,
                timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="proprietary",
            ),
        )
    )
    found = retriever.search("真夜中の合言葉", top_k=5)

    assert found
    assert any("真夜中" in r.chunk.content for r in found)


def test_a_store_that_did_not_only_append_is_rebuilt_not_extended() -> None:
    """The fast path is valid only while the old chunks are still a prefix.

    The dangerous shape is a store that *replaced* its contents and ended up
    with more chunks than before - a compaction, or a re-ingestion of changed
    files. The count went up, so a check that only looks at the count reads it
    as an append and never re-reads the chunks that changed underneath it,
    leaving postings that describe text nobody holds any more.
    """

    store = _store()
    retriever = _retriever(store)
    for i in range(8):
        store.add(_document(i))
    retriever.search("収益化の方針", top_k=5)

    store.clear()
    for i in range(12):
        # Different documents, and more of them than were indexed before.
        store.add(
            Document(
                content=f"入れ替えた本文 {i}: 掲載順は売らないという約束",
                provenance=Provenance(
                    source="github",
                    repository=_REPOS[i % len(_REPOS)],
                    path=f"docs/replaced{i}.md",
                    commit_sha="1" * 40,
                    timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )

    held = tuple(store.chunks())
    rebuilt = _retriever(store)
    rebuilt._ensure_index()

    assert retriever.search("掲載順は売らない", top_k=5), "the new text must be findable"
    assert list(retriever._chunks) == list(held)
    assert retriever._lengths == rebuilt._lengths
    assert retriever._document_frequency == rebuilt._document_frequency
    assert _answers(retriever) == _answers(rebuilt)


def test_the_candidate_index_stays_in_step_with_the_positions() -> None:
    """The shortlist hands back positions into the retriever's own list.

    Off-by-one there is the quiet kind of wrong: the scores are right and the
    chunks are the *neighbours* of the right ones. Comparing against a full
    scan cannot catch it on its own, because a shortlist is allowed to return
    a different member of a run of equal scores. So the invariant is checked
    directly instead: a term that appears in exactly one chunk must shortlist
    that chunk and no other.
    """

    if not fts5_available():
        return

    store = _store()
    retriever = _retriever(store)
    for i in range(16):
        store.add(_document(i))
        retriever._ensure_index()

    # One document, added last, carrying a word nothing else uses. Its
    # position is therefore the highest - exactly where an append that
    # mis-numbers by one lands on the wrong row.
    store.add(
        Document(
            content="真夜中の合言葉についての決まりを書いた節",
            provenance=Provenance(
                source="github",
                repository="owner/alpha",
                path="docs/unique.md",
                commit_sha="2" * 40,
                timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="proprietary",
            ),
        )
    )
    retriever._ensure_index()

    from sidra_ai.retrieval.search import tokenize

    rare = [t for t in tokenize("真夜中") if t]
    assert rare, "the probe needs a term to look for"
    positions = retriever.candidate_source.positions(tuple(rare), limit=5)
    assert positions is not None, "the shortlist must have answered"
    assert positions, "the shortlist must have found the one chunk that matches"
    for position in positions:
        assert "真夜中" in retriever._chunks[position].content, (
            "the shortlist named a position whose chunk does not contain the term"
        )
