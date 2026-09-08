"""A vector's length belongs to the vector, not to every comparison of it.

Ranking N candidates against one query calls a cosine N times, and the
straightforward cosine recomputes both lengths on every call: the query's N
times over, and each chunk's every time that chunk is ever ranked - even
though the chunk's vector is memoised precisely because it does not change.
Over 384 dimensions that is two thirds of the arithmetic in the ranking step,
and the ranking step is what a warm query spends its time on once the vector
memo has removed the model calls.

Two things are pinned, and they are different claims:

* **The answers do not move.** ``cosine_with_norms`` is the same dot product
  over the same product of the same two lengths, so it must agree with
  ``cosine`` exactly - not approximately. Checked on adversarial shapes as
  well as ordinary ones, because "close enough" here would mean a ranking
  that flips on ties.
* **The work is actually saved.** Counted, not timed: how many square roots a
  repeat query performs. A rewrite that quietly goes back to computing
  lengths per comparison passes the first check and fails this one.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.documents import (  # noqa: E402
    Document,
    Provenance,
    SourceType,
    TrustLevel,
)
from sidra_ai.retrieval import embedding as embedding_module  # noqa: E402
from sidra_ai.retrieval.embedding import (  # noqa: E402
    EmbeddingBackend,
    EmbeddingRetriever,
    cosine,
    cosine_with_norms,
    vector_norm,
)
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

_REPO = "tukemen-rgb/sidra-ai"
_CANDIDATES = 40


class _WordCountBackend(EmbeddingBackend):
    """Deterministic, dependency-free, and deliberately *not* unit length.

    The real model normalises its output, which would make every length 1.0
    and hide an error in the bookkeeping behind a coincidence. These vectors
    have lengths that differ, so a chunk's length being paired with the wrong
    chunk changes the answer and the equality check above notices.
    """

    name = "word-count"

    def available(self) -> bool:
        return True

    def encode(self, texts: Sequence[str]) -> list[Sequence[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 16
            for index, character in enumerate(text):
                vector[ord(character) % 16] += 1.0 + (index % 3)
            vectors.append(vector)
        return vectors


def _store() -> DocumentStore:
    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    for i in range(_CANDIDATES):
        store.add(
            Document(
                content=(
                    f"第 {i} 章。収益化の方針と審査の基準について。"
                    + "掲載順は売らない。個人情報は公開の場所へ置かない。" * (2 + i % 5)
                ),
                provenance=Provenance(
                    source="github",
                    repository=_REPO,
                    path=f"docs/part{i}.md",
                    commit_sha="0" * 40,
                    timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )
    return store


def _retriever() -> EmbeddingRetriever:
    return EmbeddingRetriever(BM25Retriever(_store()), _WordCountBackend())


# ---------------------------------------------------------------- equality


def test_supplying_the_lengths_gives_the_identical_number() -> None:
    """Bit-for-bit, not close: a ranking can turn on the last bit."""

    backend = _WordCountBackend()
    texts = [
        "収益化の方針",
        "審査の基準について書いた長めの文章。" * 7,
        "x",
        "まったく別の話題、たとえば釣りゲームの当たり判定。",
        "収益化の方針と審査の基準",
    ]
    vectors = backend.encode(texts)
    query = vectors[0]
    query_norm = vector_norm(query)

    for other in vectors:
        assert cosine_with_norms(
            query, query_norm, other, vector_norm(other)
        ) == cosine(query, other)


def test_the_degenerate_cases_agree_too() -> None:
    """Zero vectors and mismatched lengths are where the two could diverge."""

    zero = [0.0, 0.0, 0.0]
    ordinary = [1.0, 2.0, 3.0]
    shorter = [1.0, 2.0]

    for a, b in ((zero, ordinary), (ordinary, zero), (zero, zero),
                 (ordinary, shorter), (shorter, ordinary)):
        assert cosine_with_norms(a, vector_norm(a), b, vector_norm(b)) == cosine(a, b)


def test_the_semantic_order_is_the_one_the_plain_cosine_would_produce() -> None:
    """The whole candidate set, ordered both ways, must come out the same.

    The equality tests above compare one number at a time. This compares the
    thing the number is *for*: a sort over every candidate a real search
    ranked. A bookkeeping error - a chunk paired with another chunk's length -
    survives a per-number check and shows up here as a different order.
    """

    retriever = _retriever()
    ask = "収益化の方針と審査の基準"
    retriever.search(ask, top_k=5)  # populates the memo with the candidates

    backend = _WordCountBackend()
    query_vector = backend.encode([ask])[0]
    query_norm = vector_norm(query_vector)

    texts = list(retriever._vectors)
    assert len(texts) >= 20, "too few candidates for an order to mean anything"

    by_plain = sorted(
        texts, key=lambda t: (-cosine(query_vector, retriever._vectors[t]), t)
    )
    by_cached = sorted(
        texts,
        key=lambda t: (
            -cosine_with_norms(
                query_vector, query_norm, retriever._vectors[t], retriever._norms[t]
            ),
            t,
        ),
    )
    assert by_cached == by_plain


class _PlainCosineRetriever(EmbeddingRetriever):
    """The same retriever, ranking the way it did before the lengths were cached."""

    def _semantic_order(self, query_vector, chunk_vectors, chunk_norms):
        return sorted(
            range(len(chunk_vectors)),
            key=lambda i: cosine(query_vector, chunk_vectors[i]),
            reverse=True,
        )


def test_search_returns_what_the_plain_cosine_version_returns() -> None:
    """The results themselves, against a retriever that recomputes the lengths.

    This is the check the per-number ones cannot make. Pairing each chunk with
    the *wrong* chunk's length still produces numbers that individually equal
    a cosine of something, so every equality test passes while the search
    returns a different answer. Two retrievers over the same store, differing
    only in that one step, must agree on every query.
    """

    store = _store()
    backend = _WordCountBackend()
    cached = EmbeddingRetriever(BM25Retriever(store), backend)
    plain = _PlainCosineRetriever(BM25Retriever(store), backend)

    asks = [
        "収益化の方針",
        "審査の基準",
        "個人情報は公開の場所へ置かない",
        "掲載順",
        "第 7 章",
    ]
    for ask in asks:
        got = [r.chunk.chunk_id for r in cached.search(ask, top_k=5)]
        want = [r.chunk.chunk_id for r in plain.search(ask, top_k=5)]
        assert got, f"{ask!r} returned nothing - the fixture is not exercising this"
        assert got == want, f"{ask!r}: {got} against {want}"


# ------------------------------------------------------------------- work


def _sqrt_counting_math(counter: dict):
    class _Math:
        def __getattr__(self, name):
            return getattr(math, name)

        @staticmethod
        def sqrt(value):
            counter["n"] += 1
            return math.sqrt(value)

    return _Math()


def test_a_warm_query_takes_one_square_root_not_two_per_candidate(
    monkeypatch,
) -> None:
    """The saving, counted. Machine load cannot move this number."""

    retriever = _retriever()
    ask = "収益化の方針と審査の基準"
    first = retriever.search(ask, top_k=5)
    assert first, "the fixture must return results"
    candidates = len(retriever._vectors)
    assert candidates >= 20, (
        f"only {candidates} candidates were ranked - too few for the "
        "difference between one root and two per candidate to mean anything"
    )

    counter = {"n": 0}
    monkeypatch.setattr(embedding_module, "math", _sqrt_counting_math(counter))
    retriever.search(ask, top_k=5)

    # One for the query. Every chunk length was computed when its vector was,
    # and both are still cached.
    assert counter["n"] == 1, (
        f"{counter['n']} square roots for {candidates} cached candidates; "
        "one per query is the whole point"
    )


def test_clearing_the_memo_costs_the_lengths_too_and_stays_correct() -> None:
    """The cap drops vectors; a length left behind would describe the wrong one."""

    retriever = _retriever()
    ask = "収益化の方針"
    before = [r.chunk.chunk_id for r in retriever.search(ask, top_k=5)]

    retriever._vector_cache_max = 1  # force the clear on the next miss
    retriever.search("まったく別の質問、釣りの当たり判定について", top_k=5)

    assert set(retriever._norms) == set(retriever._vectors), (
        "a length survived without its vector, or the reverse"
    )

    retriever._vector_cache_max = 200_000
    after = [r.chunk.chunk_id for r in retriever.search(ask, top_k=5)]
    assert after == before, "results changed after the memo was cleared"
