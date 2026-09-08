"""The semantic seam, and the promise that no weights is still a working state.

Part (1) of the approved embedding work. The model arrives in part (2); what
is pinned here is the plumbing around it, because that is what can quietly
break the two things v0.1 already guarantees: that the service runs on a
clean machine, and that retrieval filters are access scope rather than
ranking hints.

The backend used here is deterministic and dependency-free on purpose. A
test that needed model weights would be a test that does not run on the
machine this promise is about.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import pytest

from sidra_ai.documents import Chunk, Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.embedding import (
    EmbeddingBackend,
    EmbeddingRetriever,
    NoEmbeddingBackend,
    cosine,
)
from sidra_ai.retrieval.search import BM25Retriever, Retriever, SearchResult

REPO_A = "tukemen-rgb/site"
REPO_B = "tukemen-rgb/Fg"


def _provenance(repository: str, path: str) -> Provenance:
    return Provenance(
        source="github",
        repository=repository,
        path=path,
        commit_sha="a" * 40,
        timestamp=datetime.now(timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="MIT",
    )


class _StubRetriever(Retriever):
    """Returns a fixed list, and records what scope it was asked for."""

    def __init__(self, results: Sequence[SearchResult]) -> None:
        self._results = list(results)
        self.calls: list[dict] = []

    def search(self, query, *, top_k=5, repositories=None, source_types=None,
               min_score=0.0):
        self.calls.append({
            "query": query, "top_k": top_k, "repositories": repositories,
            "source_types": None if source_types is None else tuple(source_types),
            "min_score": min_score,
        })
        return self._results[:top_k]


class _ReverseBackend(EmbeddingBackend):
    """Deterministic backend that ranks the lexical list exactly backwards.

    Nothing about it is realistic; that is the point. If fusion is wired up,
    an order this hostile to the lexical one has to show in the output, and
    if it does not, the semantic pass is not running.
    """

    name = "reverse-stub"

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def encode(self, texts: Sequence[str]) -> list[Sequence[float]]:
        self.calls += 1
        # texts[0] is the query. Give later chunks higher similarity.
        return [[1.0, 0.0]] + [
            [1.0, float(i)] for i in range(len(texts) - 1, 0, -1)
        ]


class _BrokenBackend(EmbeddingBackend):
    name = "broken-stub"

    def available(self) -> bool:
        return True

    def encode(self, texts: Sequence[str]) -> list[Sequence[float]]:
        raise RuntimeError("weights are corrupt")


def _results(n: int) -> list[SearchResult]:
    out = []
    for i in range(n):
        chunk = Chunk(
            content=f"chunk {i}",
            provenance=_provenance(REPO_A, f"docs/{i}.md"),
            document_id=f"doc-{i}",
            index=0,
        )
        out.append(SearchResult(chunk=chunk, score=float(n - i)))
    return out


# --- no weights is a supported state -----------------------------------


def test_default_backend_reports_itself_absent() -> None:
    assert NoEmbeddingBackend().available() is False
    assert EmbeddingRetriever(_StubRetriever([])).backend_name == "none"


def test_without_a_backend_it_is_the_lexical_retriever() -> None:
    """Same results, same order, same scores. Not merely 'still works'."""

    lexical = _StubRetriever(_results(5))
    retriever = EmbeddingRetriever(lexical)

    got = retriever.search("q", top_k=3)

    assert [r.content for r in got] == ["chunk 0", "chunk 1", "chunk 2"]
    assert [r.score for r in got] == [5.0, 4.0, 3.0]
    assert lexical.calls[0]["top_k"] == 3, "no candidate widening when disabled"


def test_a_backend_that_raises_on_encode_degrades_ranking_not_availability() -> None:
    lexical = _StubRetriever(_results(4))
    retriever = EmbeddingRetriever(lexical, _BrokenBackend())

    got = retriever.search("q", top_k=2)

    assert [r.content for r in got] == ["chunk 0", "chunk 1"]


def test_a_backend_that_returns_the_wrong_shape_is_ignored() -> None:
    class _ShortBackend(EmbeddingBackend):
        name = "short-stub"

        def available(self) -> bool:
            return True

        def encode(self, texts):
            return [[1.0, 0.0]]  # missing the chunk vectors

    got = EmbeddingRetriever(_StubRetriever(_results(3)), _ShortBackend()).search("q")

    assert [r.content for r in got] == ["chunk 0", "chunk 1", "chunk 2"]


def test_an_available_check_that_raises_counts_as_unavailable() -> None:
    class _AngryBackend(EmbeddingBackend):
        name = "angry-stub"

        def available(self) -> bool:
            raise OSError("model directory unreadable")

        def encode(self, texts):  # pragma: no cover - never reached
            raise AssertionError

    retriever = EmbeddingRetriever(_StubRetriever(_results(2)), _AngryBackend())

    assert retriever.semantic_enabled() is False
    assert [r.content for r in retriever.search("q")] == ["chunk 0", "chunk 1"]


# --- the semantic pass actually runs -----------------------------------


def test_the_semantic_pass_reorders_the_lexical_list() -> None:
    backend = _ReverseBackend()
    retriever = EmbeddingRetriever(_StubRetriever(_results(6)), backend)

    got = retriever.search("q", top_k=6)

    assert backend.calls == 1
    assert [r.content for r in got] != [f"chunk {i}" for i in range(6)]
    assert {r.content for r in got} == {f"chunk {i}" for i in range(6)}


def test_candidates_are_widened_before_fusion() -> None:
    """Semantic reordering can only promote what it was given to look at."""

    lexical = _StubRetriever(_results(20))
    retriever = EmbeddingRetriever(lexical, _ReverseBackend(), candidate_multiplier=4)

    retriever.search("q", top_k=3)

    assert lexical.calls[0]["top_k"] == 12


def test_scores_stay_in_lexical_units() -> None:
    """A fused score would look like a BM25 score and not be one."""

    retriever = EmbeddingRetriever(_StubRetriever(_results(4)), _ReverseBackend())

    for result in retriever.search("q", top_k=4):
        assert result.score in {4.0, 3.0, 2.0, 1.0}


# --- filters are scope, not hints --------------------------------------


def test_scope_is_passed_through_to_the_only_place_that_enforces_it() -> None:
    lexical = _StubRetriever(_results(4))
    retriever = EmbeddingRetriever(lexical, _ReverseBackend())

    retriever.search("q", top_k=2, repositories=[REPO_A],
                     source_types=[SourceType.DOCS])

    call = lexical.calls[0]
    assert call["repositories"] == [REPO_A]
    assert call["source_types"] == (SourceType.DOCS,)


def test_a_one_shot_source_type_iterable_survives_both_passes() -> None:
    """A generator consumed by the first pass would silently widen the second."""

    lexical = _StubRetriever(_results(3))
    retriever = EmbeddingRetriever(lexical, _ReverseBackend())

    retriever.search("q", source_types=(t for t in (SourceType.DOCS,)))

    assert lexical.calls[0]["source_types"] == (SourceType.DOCS,)


def test_empty_scope_still_means_search_nothing() -> None:
    lexical = _StubRetriever([])
    retriever = EmbeddingRetriever(lexical, _ReverseBackend())

    assert retriever.search("q", repositories=[]) == []


# --- min_score is not reinterpreted ------------------------------------


def test_a_threshold_disables_the_semantic_pass_rather_than_being_rescored() -> None:
    backend = _ReverseBackend()
    lexical = _StubRetriever(_results(5))
    retriever = EmbeddingRetriever(lexical, backend)

    got = retriever.search("q", top_k=3, min_score=2.5)

    assert retriever.semantic_enabled(min_score=2.5) is False
    assert backend.calls == 0, "encoding a query whose threshold we cannot honour"
    assert lexical.calls[0]["min_score"] == 2.5
    assert [r.content for r in got] == ["chunk 0", "chunk 1", "chunk 2"]


# --- contract with the rest of the system ------------------------------


def test_it_is_a_retriever() -> None:
    assert isinstance(EmbeddingRetriever(_StubRetriever([])), Retriever)


def test_provenance_survives_the_semantic_pass(store, gate) -> None:
    """Citation is the point of the system; reordering must not strip it."""

    document = Document(
        content="GameYard は投稿を無料にしている。多言語化はしない。",
        provenance=_provenance(REPO_B, "docs/policy.md"),
    )
    result, screened = gate.screen_document(document)
    assert screened is not None, result.decision
    store.add(screened, gate_result=result)
    retriever = EmbeddingRetriever(BM25Retriever(store), _ReverseBackend())

    got = retriever.search("投稿", top_k=3)

    assert got, "the corpus should have matched"
    for result in got:
        assert result.provenance.repository == REPO_B
        assert result.provenance.path == "docs/policy.md"
        assert result.provenance.commit_sha


def test_empty_query_returns_nothing_rather_than_raising() -> None:
    assert EmbeddingRetriever(_StubRetriever([]), _ReverseBackend()).search("") == []


# --- the similarity helper ---------------------------------------------


@pytest.mark.parametrize("a,b,expected", [
    ([1.0, 0.0], [1.0, 0.0], 1.0),
    ([1.0, 0.0], [0.0, 1.0], 0.0),
    ([0.0, 0.0], [1.0, 1.0], 0.0),      # zero vector, not ZeroDivisionError
    ([1.0], [1.0, 0.0], 0.0),           # mismatched length is not comparable
])
def test_cosine(a, b, expected) -> None:
    assert cosine(a, b) == pytest.approx(expected)


# --- the configured backend --------------------------------------------


def test_a_backend_with_no_path_is_unavailable_and_says_why() -> None:
    from sidra_ai.retrieval.embedding import SentenceTransformerBackend

    backend = SentenceTransformerBackend("")

    assert backend.available() is False
    assert backend.unavailable_reason == "no model path configured"


def test_a_missing_model_directory_is_unavailable_not_a_download(tmp_path) -> None:
    """A mistyped path must not become a network fetch."""

    from sidra_ai.retrieval.embedding import SentenceTransformerBackend

    backend = SentenceTransformerBackend(tmp_path / "not-here")

    assert backend.available() is False
    assert "directory" in backend.unavailable_reason


def test_the_unavailable_reason_never_carries_the_path(tmp_path) -> None:
    """Deployment topology does not belong in a status string."""

    from sidra_ai.retrieval.embedding import SentenceTransformerBackend

    secret_dir = tmp_path / "srv-internal-weights"
    backend = SentenceTransformerBackend(secret_dir)
    backend.available()

    assert "srv-internal-weights" not in backend.unavailable_reason


def test_prefixes_are_applied_asymmetrically() -> None:
    """texts[0] is the query; everything after it is a passage."""

    from sidra_ai.retrieval.embedding import SentenceTransformerBackend

    seen: list[list[str]] = []
    class _Recorder(SentenceTransformerBackend):
        def available(self) -> bool:
            return True

    backend = _Recorder("/nonexistent", query_prefix="query: ",
                        passage_prefix="passage: ")

    class _Model:
        def encode(self, texts):
            seen.append(list(texts))
            return [[1.0, 0.0] for _ in texts]

    backend._model = _Model()
    backend.encode(["どれくらい費用がかかりますか", "投稿は無料", "多言語化はしない"])

    assert seen == [[
        "query: どれくらい費用がかかりますか",
        "passage: 投稿は無料",
        "passage: 多言語化はしない",
    ]]


def test_encoding_nothing_returns_nothing() -> None:
    from sidra_ai.retrieval.embedding import SentenceTransformerBackend

    backend = SentenceTransformerBackend("/nonexistent")
    backend._model = object()

    assert backend.encode([]) == []


def test_settings_without_a_path_select_no_backend() -> None:
    from sidra_ai.config.settings import Settings
    from sidra_ai.retrieval.embedding import backend_from_settings

    assert backend_from_settings(Settings()).name == "none"


def test_settings_with_a_path_select_the_local_backend() -> None:
    from dataclasses import replace

    from sidra_ai.config.settings import Settings
    from sidra_ai.retrieval.embedding import backend_from_settings

    configured = replace(Settings(), embedding_model_path="/srv/sidra/model",
                         embedding_query_prefix="query: ")
    backend = backend_from_settings(configured)

    assert backend.name == "sentence-transformers"
    assert backend._query_prefix == "query: "


def test_settings_report_whether_embedding_is_configured_not_where() -> None:
    from dataclasses import replace

    from sidra_ai.config.settings import Settings

    rendered = str(replace(Settings(), embedding_model_path="/srv/secret/weights").redacted_dict())

    assert "embedding_configured': True" in rendered
    assert "/srv/secret/weights" not in rendered


def test_the_window_decides_what_the_model_is_allowed_to_see(store, gate) -> None:
    """The window is the ceiling on what the semantic pass can do at all.

    The pass reorders candidates; it never widens them. A chunk below the
    window is invisible to the model no matter how well the model would have
    scored it - and the questions embeddings exist to rescue are exactly the
    ones BM25 ranks worst. Measured 2026-09-08 on the real five-repository
    corpus: the chunks answering ``submission-fee``,
    ``mkt-what-is-this-repo`` and ``cy-payments`` sit at lexical rank 189,
    131 and 111, all outside the window of 50 that used to be the default.

    This test asserts the mechanism directly - how many candidates reach the
    backend - rather than a ranking outcome, because the ranking outcome also
    depends on fusion, and a test that mixes the two cannot say which failed.

    **The promotion half is deliberately not reconstructed here.** Two drafts
    of it passed only after the fixture had been tuned - a stub backend that
    singles out one document leaves every distractor tied, so reciprocal rank
    fusion keeps whatever BM25 put on top, and making the assertion hold
    meant choosing burial depths and stub scores until it did. That is
    fitting the test to the wish. The evidence that widening promotes real
    answers is the judge on the real corpus, recorded in
    ``docs/OUTCOMES.md``: direct-word answers 12 -> 13 and answered 17 -> 19
    when the window went from 50 to 200.
    """

    def _add(text: str, path: str) -> None:
        document = Document(content=text, provenance=_provenance(REPO_B, path))
        result, screened = gate.screen_document(document)
        assert screened is not None, result.decision
        store.add(screened, gate_result=result)

    for i in range(80):
        _add(f"決済 決済 決済 の話 {i}", f"docs/noise{i}.md")
    _add("決済は持たない", "docs/answer.md")

    class _Counting:
        def __init__(self) -> None:
            self.offered = 0

        def encode(self, texts):
            # texts[0] is the query; the rest are candidate passages.
            self.offered = len(texts) - 1
            return [[0.0] for _ in texts]

        def available(self):
            return True

    narrow, wide = _Counting(), _Counting()
    EmbeddingRetriever(
        BM25Retriever(store), narrow, candidate_multiplier=4
    ).search("決済", top_k=5)
    EmbeddingRetriever(
        BM25Retriever(store), wide, candidate_multiplier=40
    ).search("決済", top_k=5)

    assert narrow.offered == 20, narrow.offered
    assert wide.offered > 50, wide.offered


def test_the_default_window_is_the_measured_one(store, gate) -> None:
    """The default is the thing that ships, so the default is what is pinned.

    The window test above passes its multiplier explicitly, so it keeps
    passing if someone changes the default - which is how a measured gain
    quietly leaves the product. Measured 2026-09-08 on the five-repository
    corpus: a window of 50 answers 17 of 38 and 12 of 18 direct-word
    questions; 200 answers 19 and 13, and every window from 200 to 4,000
    answers the same 19. 40 is the first multiplier on that plateau at the
    product's ``top_k`` of 5.

    Lowering it is allowed and takes a deliberate edit here plus a reason,
    the same mechanism as the judge's floors.
    """

    document = Document(
        content="決済は持たない。", provenance=_provenance(REPO_B, "docs/a.md")
    )
    result, screened = gate.screen_document(document)
    assert screened is not None, result.decision
    store.add(screened, gate_result=result)

    class _Counting:
        def __init__(self) -> None:
            self.asked_for = 0

        def encode(self, texts):
            return [[0.0] for _ in texts]

        def available(self):
            return True

    class _Spy(BM25Retriever):
        def __init__(self, inner: BM25Retriever) -> None:
            self._inner = inner
            self.top_k_seen: list[int] = []

        def search(self, query, *, top_k=5, **kwargs):
            self.top_k_seen.append(top_k)
            return self._inner.search(query, top_k=top_k, **kwargs)

    spy = _Spy(BM25Retriever(store))
    EmbeddingRetriever(spy, _Counting()).search("決済", top_k=5)

    assert spy.top_k_seen == [200], (
        "the default semantic window must stay at the measured 200 "
        f"candidates for top_k=5; asked for {spy.top_k_seen}"
    )
