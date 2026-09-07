"""FTS5 may say WHICH chunks to score. It may never say how well they score.

C-1464 measured the whole swap and it cost an answer, because SQLite's
``bm25()`` is fixed at k1=1.2 where this corpus is tuned to k1=1.5. C-1466
keeps the scorer and borrows only the shortlist, so what these tests have to
hold is narrow and exact:

* a shortlisted search returns **what the full scan would have returned**,
  same chunks in the same order, whenever the winners are in the shortlist;
* a **filtered** search never consults the shortlist at all, because its BM25
  statistics are derived from the eligible set and a shortlist is selected out
  of it;
* every way the shortlist can fail - no FTS5, a rejected query, a source that
  raises - degrades to the full scan rather than to a thinner answer.

The one test that would make the rest meaningless if it were missing is
``test_a_shortlist_too_small_changes_the_answer``: if narrowing could never
change a result, none of the identity assertions would be evidence of
anything.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.candidates import (
    CandidateSource,
    Fts5CandidateSource,
    fts5_available,
)
from sidra_ai.retrieval.search import BM25Retriever, tokenize
from sidra_ai.retrieval.store import DocumentStore

REPO = "tukemen-rgb/site"
OTHER = "tukemen-rgb/creater-yard"

pytestmark = pytest.mark.skipif(
    not fts5_available(), reason="this SQLite build has no FTS5"
)


def _document(content: str, *, repository: str = REPO, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=repository,
            path=path,
            commit_sha="b" * 40,
            timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


#: Filler prose that repeats one term a different number of times per
#: document, so that "ranking" separates the corpus into distinct scores
#: rather than one long tie. Ties are their own case and get their own test
#: (``test_exact_ties_may_resolve_to_a_different_equal_scoring_chunk``); a
#: corpus that is nothing but ties would make every identity assertion here
#: a statement about tie-breaking instead of about ranking.
def _corpus(store: DocumentStore, count: int = 60) -> DocumentStore:
    """A corpus where one document is the obvious winner for ``retrieval``."""

    store.add(
        _document(
            "retrieval retrieval retrieval ranking policy",
            path="docs/winner.md",
        )
    )
    store.add(_document("retrieval ranking policy notes", path="docs/second.md"))
    for index in range(count):
        emphasis = " ".join(["ranking"] * (1 + index % 7))
        store.add(
            _document(
                f"{emphasis} policy filler {index} unrelated prose about deployment",
                path=f"docs/filler-{index}.md",
            )
        )
    return store


def _ids(results):
    return [r.chunk.chunk_id for r in results]


def _scores(results):
    return [round(r.score, 9) for r in results]


# --------------------------------------------------------------- identity


def test_shortlisted_search_returns_exactly_the_full_scan_result(
    store: DocumentStore,
) -> None:
    _corpus(store)
    plain = BM25Retriever(store)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=40
    )
    for query in ("retrieval", "ranking policy", "policy", "deployment prose"):
        want = plain.search(query, top_k=5)
        got = hybrid.search(query, top_k=5)
        assert _ids(got) == _ids(want), query


def test_scores_are_identical_not_merely_the_same_order(
    store: DocumentStore,
) -> None:
    """A shortlist must not perturb the number, or ``min_score`` moves with it."""

    _corpus(store)
    plain = BM25Retriever(store)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=40
    )
    assert _scores(hybrid.search("retrieval", top_k=5)) == _scores(
        plain.search("retrieval", top_k=5)
    )


def test_exact_ties_may_resolve_to_a_different_equal_scoring_chunk(
    store: DocumentStore,
) -> None:
    """The one difference from a full scan, pinned rather than papered over.

    BM25 breaks exact ties by chunk id. A shortlist that cuts through a run of
    exactly equal scores offers a different set to break ties among, so the
    tail can name different chunks *at the same score*. A bigger pool does not
    fix this and is not supposed to: nothing is displaced by a worse result.
    """

    for index in range(60):
        store.add(_document("ranking policy", path=f"docs/tie-{index}.md"))
    plain = BM25Retriever(store).search("ranking policy", top_k=5)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=40
    ).search("ranking policy", top_k=5)

    assert len({round(r.score, 9) for r in plain}) == 1, "the corpus must tie"
    assert _ids(hybrid) != _ids(plain)
    assert _scores(hybrid) == _scores(plain)


def test_a_shortlist_too_small_changes_the_answer(store: DocumentStore) -> None:
    """The both-directions check: narrowing has to be capable of hurting.

    Every other test here asserts that results did not change. Those are only
    evidence if a shortlist can change them at all - otherwise they would pass
    against a retriever that ignored the candidate source entirely.
    """

    _corpus(store)
    plain = BM25Retriever(store)
    starved = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=1
    )
    assert _ids(starved.search("ranking policy", top_k=5)) != _ids(
        plain.search("ranking policy", top_k=5)
    )


def test_top_result_survives_the_smallest_useful_pool(store: DocumentStore) -> None:
    _corpus(store)
    plain = BM25Retriever(store)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=5
    )
    assert _ids(hybrid.search("retrieval", top_k=1)) == _ids(
        plain.search("retrieval", top_k=1)
    )


# ----------------------------------------------------------------- scope


class _Recording(CandidateSource):
    """A source that records every question asked of it and always declines."""

    def __init__(self) -> None:
        self.asked: list[tuple[tuple[str, ...], int]] = []
        self.reindexed = 0

    def reindex(self, token_lists) -> None:
        self.reindexed += 1
        list(token_lists)

    def positions(self, query_terms, *, limit):
        self.asked.append((tuple(query_terms), limit))
        return None


def test_a_filtered_search_never_consults_the_shortlist(
    store: DocumentStore,
) -> None:
    """Filtered statistics come from the eligible set; a shortlist is not it."""

    _corpus(store)
    store.add(_document("retrieval elsewhere", repository=OTHER, path="docs/o.md"))
    recorder = _Recording()
    retriever = BM25Retriever(store, candidate_source=recorder)

    retriever.search("retrieval", top_k=5, repositories=[REPO])
    assert recorder.asked == []

    retriever.search("retrieval", top_k=5, source_types=[SourceType.DOCS])
    assert recorder.asked == []

    retriever.search("retrieval", top_k=5)
    assert len(recorder.asked) == 1


def test_a_filtered_search_is_unchanged_by_attaching_a_source(
    store: DocumentStore,
) -> None:
    _corpus(store)
    store.add(_document("retrieval elsewhere", repository=OTHER, path="docs/o.md"))
    plain = BM25Retriever(store)
    hybrid = BM25Retriever(store, candidate_source=Fts5CandidateSource())
    assert _scores(hybrid.search("retrieval", top_k=5, repositories=[REPO])) == _scores(
        plain.search("retrieval", top_k=5, repositories=[REPO])
    )


def test_the_pool_is_derived_from_top_k_when_not_given(store: DocumentStore) -> None:
    _corpus(store)
    recorder = _Recording()
    BM25Retriever(store, candidate_source=recorder).search("retrieval", top_k=3)
    assert recorder.asked[0][1] % 3 == 0
    assert recorder.asked[0][1] > 3


def test_an_explicit_pool_overrides_the_multiplier(store: DocumentStore) -> None:
    _corpus(store)
    recorder = _Recording()
    BM25Retriever(store, candidate_source=recorder, candidate_pool=7).search(
        "retrieval", top_k=3
    )
    assert recorder.asked[0][1] == 7


def test_the_source_is_asked_only_for_corpus_present_terms(
    store: DocumentStore,
) -> None:
    """The retriever bounds query terms before asking; the source sees that set."""

    _corpus(store)
    recorder = _Recording()
    BM25Retriever(store, candidate_source=recorder).search("retrieval zzzznotacorpus")
    assert recorder.asked[0][0] == ("retrieval",)


# ------------------------------------------------------------ degradation


class _Broken(CandidateSource):
    def reindex(self, token_lists) -> None:
        list(token_lists)

    def positions(self, query_terms, *, limit):
        return None


def test_a_declining_source_gives_the_full_scan_result(store: DocumentStore) -> None:
    _corpus(store)
    plain = BM25Retriever(store)
    declining = BM25Retriever(store, candidate_source=_Broken())
    assert _ids(declining.search("ranking policy", top_k=5)) == _ids(
        plain.search("ranking policy", top_k=5)
    )


def test_a_source_that_failed_to_build_declines(store: DocumentStore) -> None:
    _corpus(store)
    source = Fts5CandidateSource()
    source._db = None
    assert source.positions(("retrieval",), limit=10) is None


def test_a_query_fts5_cannot_parse_declines_rather_than_returning_nothing() -> None:
    source = Fts5CandidateSource([["alpha"], ["beta"]])
    assert source.positions(('al"pha OR NEAR(', "beta"), limit=1) is not None
    source._db.close()
    assert source.positions(("alpha",), limit=1) is None


def test_asking_for_the_whole_corpus_declines(store: DocumentStore) -> None:
    """A pool at or above the corpus size cannot narrow anything."""

    source = Fts5CandidateSource([["alpha"], ["beta"], ["gamma"]])
    assert source.positions(("alpha",), limit=3) is None
    assert source.positions(("alpha",), limit=2) == [0]


def test_an_empty_query_declines() -> None:
    source = Fts5CandidateSource([["alpha"]])
    assert source.positions((), limit=5) is None


def test_a_zero_pool_declines() -> None:
    source = Fts5CandidateSource([["alpha"], ["beta"]])
    assert source.positions(("alpha",), limit=0) is None


# ------------------------------------------------------------- freshness


def test_the_shortlist_is_rebuilt_when_the_corpus_grows(
    store: DocumentStore,
) -> None:
    """A stale shortlist would hide new documents from every search."""

    _corpus(store, count=10)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=20
    )
    hybrid.search("retrieval", top_k=5)

    store.add(
        _document("retrieval retrieval retrieval retrieval", path="docs/newest.md")
    )
    plain = BM25Retriever(store)
    assert _ids(hybrid.search("retrieval", top_k=1)) == _ids(
        plain.search("retrieval", top_k=1)
    )
    assert "newest" in hybrid.search("retrieval", top_k=1)[0].provenance.path


def test_reindex_is_given_tokens_not_chunks(store: DocumentStore) -> None:
    """Tokenizing is the whole cost of the shortlist and it is already paid."""

    _corpus(store, count=3)

    seen: list[list[str]] = []

    class _Capture(CandidateSource):
        def reindex(self, token_lists) -> None:
            seen.extend(list(t) for t in token_lists)

        def positions(self, query_terms, *, limit):
            return None

    BM25Retriever(store, candidate_source=_Capture()).search("retrieval")
    assert len(seen) == len(tuple(store.chunks()))
    assert seen[0] == tokenize(tuple(store.chunks())[0].content)


def test_from_chunks_matches_a_token_built_source(store: DocumentStore) -> None:
    _corpus(store, count=5)
    chunks = tuple(store.chunks())
    by_chunk = Fts5CandidateSource.from_chunks(chunks)
    by_token = Fts5CandidateSource([tokenize(c.content) for c in chunks])
    assert by_chunk.positions(("retrieval",), limit=3) == by_token.positions(
        ("retrieval",), limit=3
    )


# ------------------------------------------------------------- threading


def test_the_shortlist_answers_from_a_thread_that_did_not_build_it(
    store: DocumentStore,
) -> None:
    """The defect this catches took out 26 tests, and none of them was about FTS5.

    The API builds its index while starting up and answers on Starlette's
    worker threads. A stock ``sqlite3.connect`` refuses to be used from a
    second thread, so attaching a shortlist turned every HTTP question into a
    ``ProgrammingError`` - a failure mode a pure-Python index simply does not
    have, and one no single-threaded test would ever have shown.
    """

    import threading

    _corpus(store, count=10)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=20
    )
    hybrid.search("retrieval", top_k=5)  # build here...

    outcome: list[object] = []

    def _elsewhere() -> None:
        try:
            outcome.append(_ids(hybrid.search("retrieval", top_k=5)))
        except Exception as exc:  # noqa: BLE001 - the failure is the finding
            outcome.append(exc)

    worker = threading.Thread(target=_elsewhere)
    worker.start()
    worker.join(timeout=30)

    assert outcome and not isinstance(outcome[0], Exception), outcome
    assert outcome[0] == _ids(BM25Retriever(store).search("retrieval", top_k=5))


def test_concurrent_searches_all_return_the_full_scan_result(
    store: DocumentStore,
) -> None:
    """Many threads on one connection, which is the case a lock has to cover."""

    import threading

    _corpus(store, count=30)
    hybrid = BM25Retriever(
        store, candidate_source=Fts5CandidateSource(), candidate_pool=25
    )
    want = _ids(BM25Retriever(store).search("retrieval", top_k=5))

    results: list[object] = []
    barrier = threading.Barrier(8)

    def _hammer() -> None:
        try:
            barrier.wait(timeout=30)
            results.append(_ids(hybrid.search("retrieval", top_k=5)))
        except Exception as exc:  # noqa: BLE001
            results.append(exc)

    workers = [threading.Thread(target=_hammer) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)

    assert len(results) == 8
    assert all(r == want for r in results), results


def test_a_rebuild_racing_a_search_never_answers_from_a_closed_index(
    store: DocumentStore,
) -> None:
    """``reindex`` closes the connection; a search must not meet it mid-swap."""

    import threading

    _corpus(store, count=20)
    source = Fts5CandidateSource.from_chunks(store.chunks())
    tokens = [tokenize(c.content) for c in store.chunks()]
    failures: list[Exception] = []
    stop = threading.Event()

    def _rebuild() -> None:
        while not stop.is_set():
            try:
                source.reindex(tokens)
            except Exception as exc:  # noqa: BLE001
                failures.append(exc)

    def _query() -> None:
        for _ in range(200):
            try:
                source.positions(("retrieval",), limit=5)
            except Exception as exc:  # noqa: BLE001
                failures.append(exc)

    rebuilder = threading.Thread(target=_rebuild, daemon=True)
    rebuilder.start()
    querier = threading.Thread(target=_query)
    querier.start()
    querier.join(timeout=30)
    stop.set()
    rebuilder.join(timeout=30)

    assert failures == []


# ------------------------------------------------------------------ wiring


def test_the_product_path_attaches_a_shortlist(store: DocumentStore) -> None:
    from types import SimpleNamespace

    from sidra_ai.retrieval.embedding import build_retriever

    retriever = build_retriever(SimpleNamespace(embedding_model_path=""), store)
    assert isinstance(retriever.candidate_source, Fts5CandidateSource)


def test_the_product_path_ranks_identically_to_a_full_scan(
    store: DocumentStore,
) -> None:
    from types import SimpleNamespace

    from sidra_ai.retrieval.embedding import build_retriever

    _corpus(store)
    product = build_retriever(SimpleNamespace(embedding_model_path=""), store)
    plain = BM25Retriever(store)
    for query in ("retrieval", "ranking policy", "deployment", "filler 3"):
        assert _ids(product.search(query, top_k=5)) == _ids(
            plain.search(query, top_k=5)
        ), query


def test_fts5_available_reports_a_real_answer() -> None:
    assert fts5_available() is True
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
