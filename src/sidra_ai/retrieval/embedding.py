"""Semantic retrieval, wired so that having no model weights is normal.

Why this exists: the answerable rate for questions asked in the operator's
own words is 14.3%, against 63.6% for questions that reuse the document's
wording (``docs/OUTCOMES.md``). BM25 matches words, so a reader who does not
already know how a document phrases something gets nothing. Three cheaper
fixes were measured and none worked; one made direct wording worse.

This module is part (1) of that change: the seam and the fallback, not the
model. It carries a real fusion path, exercised by a deterministic backend
in the tests, so part (2) has somewhere to plug a local model into rather
than a sketch.

Two properties are deliberate, and both are about not breaking what works:

*No weights is the default and stays supported.* ``EmbeddingRetriever``
with no backend is exactly ``BM25Retriever`` - same results, same scores.
v0.1's promise that the service runs on a clean machine survives; a missing
model degrades ranking, never availability.

*A caller's ``min_score`` disables the semantic pass rather than being
reinterpreted.* The threshold is expressed in BM25 units. Fused ranks are
not those units, and quietly rescoring against a threshold somebody chose
for a different scale is how a filter stops meaning what its author meant.
"""

from __future__ import annotations

import threading

import abc
import math
import os
from pathlib import Path
from typing import Iterable, Sequence

from sidra_ai.documents import SourceType
from sidra_ai.retrieval.search import Retriever, SearchResult

#: Reciprocal-rank-fusion damping. 60 is the value from the original TREC
#: work; it matters only that one list cannot dominate purely by being
#: longer, and this is not tuned against our own questions on purpose -
#: tuning a constant on 18 cases we wrote would be fitting the eval.
RRF_K = 60


class EmbeddingBackend(abc.ABC):
    """Turns text into vectors, or honestly says it cannot.

    Implementations must be local: no external API, no paid dependency.
    ``available()`` exists so a backend can be constructed on a machine with
    no weights and report that fact, instead of failing at import time and
    taking the service down with it.
    """

    #: Short identifier for logs and status. Never a path or an endpoint.
    name: str = "embedding"

    @abc.abstractmethod
    def available(self) -> bool:
        """Whether this backend can encode right now."""

    @abc.abstractmethod
    def encode(self, texts: Sequence[str]) -> list[Sequence[float]]:
        """Vectors for ``texts``, one per input, all the same length."""


class NoEmbeddingBackend(EmbeddingBackend):
    """The default: there are no weights, and that is a supported state.

    Spelled out as a class rather than left as ``None`` so that "we checked
    and there is no model" and "nobody wired this up" are the same, visible
    thing.
    """

    name = "none"

    def available(self) -> bool:
        return False

    def encode(self, texts: Sequence[str]) -> list[Sequence[float]]:
        raise RuntimeError("no embedding backend is configured")


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, 0.0 for a zero vector rather than a ZeroDivision."""

    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def vector_norm(vector: Sequence[float]) -> float:
    """The length of ``vector``. Split out so it can be computed once."""

    return math.sqrt(sum(x * x for x in vector))


def cosine_with_norms(
    a: Sequence[float], norm_a: float, b: Sequence[float], norm_b: float
) -> float:
    """:func:`cosine`, with the two lengths supplied instead of recomputed.

    Identical arithmetic - the same dot product divided by the same product
    of the same two lengths - so results are bit-for-bit what :func:`cosine`
    returns, and that equality is pinned by a test over the real corpus.

    It exists because a length is a property of one vector while cosine is
    called once per *pair*. Ranking 50 candidates against one query called
    this 50 times and each call recomputed both lengths: the query's 50 times
    over, and each chunk's every time that chunk was ever ranked, though the
    chunk vector itself was memoised precisely because it does not change.
    Two thirds of the arithmetic in the ranking step was that.
    """

    if len(a) != len(b) or norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)


class EmbeddingRetriever(Retriever):
    """Lexical retrieval, with a semantic pass when weights are present.

    Composition rather than inheritance: the lexical retriever stays exactly
    itself, and can be swapped or tested alone. The store is reached through
    it, so there is one index and one place that knows about chunks.
    """

    def __init__(
        self,
        lexical: Retriever,
        backend: EmbeddingBackend | None = None,
        *,
        candidate_multiplier: int = 40,
    ) -> None:
        self._lexical = lexical
        self._backend = backend or NoEmbeddingBackend()
        #: How far down the lexical list to look for chunks the semantic pass
        #: can promote. Bounded because encoding is the expensive half.
        #:
        #: **The window is the ceiling on what semantic retrieval can do at
        #: all.** The pass reorders candidates; it never widens them. A chunk
        #: below the window is invisible to the model no matter how well the
        #: model would have scored it - and the questions embeddings exist to
        #: rescue are exactly the ones BM25 ranks worst. Measured 2026-09-08
        #: on the real five-repository corpus: the chunks answering
        #: ``submission-fee``, ``mkt-what-is-this-repo`` and ``cy-payments``
        #: sit at lexical rank 189, 131 and 111, all far outside a window of
        #: 50, while the model ranks the first two 26th and 22nd once it is
        #: allowed to see them.
        #:
        #: Swept on the 38-question set (``scripts/measure_outcomes.py``
        #: judge, weights present), window = ``top_k * multiplier`` at
        #: ``top_k`` 5, against 3,937 chunks:
        #:
        #:   mult  window  answered  direct  para  discrimination    MRR  warm
        #:     10      50        17      12     5          +28.9  0.327  24ms
        #:     20     100        17      12     5          +26.3  0.327  31ms
        #:     40     200        19      13     6          +36.8  0.342  30ms
        #:     80     400        19      13     6          +34.2  0.361  37ms
        #:    160     800        19      13     6          +34.2  0.359  44ms
        #:    320    1600        19      13     6          +34.2  0.359  50ms
        #:    800    4000        19      13     6          +34.2  0.359  50ms
        #:
        #: 40 is the *first* point on the plateau, not the best-looking row:
        #: every window from 200 to 4,000 answers the same 19, so the counts
        #: stop being evidence past 200 and what is left is a third decimal of
        #: MRR, which is not floored and not worth 7ms. Discrimination rises
        #: rather than falls, so this is not a gain bought by returning more
        #: plausible neighbours.
        #:
        #: **This reverses the note that stood here, and the reversal is a
        #: different measurement rather than a contradiction.** That note read:
        #: "Measured over the 26-question set: 10, 20, 40 and 80 all answer
        #: the same 13 questions, so the window buys nothing past 50 chunks.
        #: What widening does move is discrimination, downward (+30.8pt at 10
        #: and 20, +26.9 at 40, +23.1 at 80). 10 keeps the best
        #: discrimination, the best measured MRR (0.436 against 0.429 at 20),
        #: and half the encoding cost of 20." It was taken on a 26-question
        #: set and a smaller corpus; the set has since grown to 38 and the
        #: corpus to 3,937 chunks. Both readings are believed correct about
        #: what they measured. Anyone re-opening this must re-measure rather
        #: than pick the number they prefer from the two.
        self._candidate_multiplier = max(1, candidate_multiplier)
        #: Chunk vectors, keyed by the content that produced them.
        #:
        #: A chunk's embedding is a pure function of its text, so encoding the
        #: same passage on every query was work with a known answer. Measured
        #: on the real corpus with e5-small: search p50 **3,316 ms -> 63 ms**,
        #: because each call had been pushing 50 candidate passages through
        #: the model to rank 5 results. Only the query is genuinely new per
        #: call, and it is the one thing this never caches.
        #:
        #: Keyed by content rather than by ``chunk_id`` deliberately: the id
        #: is a position (``document_id:index``) and re-ingesting a changed
        #: file can hand the same id to different text, which would serve a
        #: stale vector. Content cannot lie about what it is.
        self._vectors: dict[str, Sequence[float]] = {}
        #: Each cached vector's length, keyed identically and cleared with it.
        #: A length depends only on the vector, and the vector is memoised
        #: because it does not change - so recomputing the length on every
        #: comparison was the same wasted work the vector memo already
        #: removed, one level down. See :func:`cosine_with_norms`.
        self._norms: dict[str, float] = {}
        #: Bound on the cache. 384-dimension vectors are ~1.5 KB each as
        #: Python floats, so this is a few hundred MB at the cap - and the
        #: cap exists for the corpus that outgrows memory, not for normal
        #: operation (the real corpus is 3,274 chunks). Cleared wholesale
        #: rather than evicted one at a time: the access pattern is a scan
        #: over whatever the lexical pass shortlisted, not a recency-skewed
        #: workload, so LRU's bookkeeping would cost more than it saves.
        self._vector_cache_max = 200_000
        #: The memo is shared by every thread the server answers from, and
        #: "clear if full, then write" is two steps. Without this a clear
        #: landing between them left a thread reading a key it had just
        #: written and finding it gone - handled, but by degrading the answer
        #: to the lexical order rather than by being correct. The lock covers
        #: only dictionary work; the model call stays outside it, so two
        #: questions still encode in parallel.
        self._vector_lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def backend_name(self) -> str:
        return self._backend.name

    def semantic_enabled(self, *, min_score: float = 0.0) -> bool:
        """Whether this call will use the semantic pass, and why not if it will not."""

        if min_score > 0.0:
            return False
        try:
            return bool(self._backend.available())
        except Exception:  # noqa: BLE001 - an unusable backend is an absent one
            return False

    # ------------------------------------------------------------------
    @property
    def store(self):
        """The one index, reached through the lexical retriever it wraps.

        Callers that need to ask what is in the corpus - a smoke check that a
        specific document was ingested, say - should not have to know which
        retriever they were handed or reach into a private attribute to find
        out.
        """

        return self._lexical.store

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        repositories: Sequence[str] | None = None,
        source_types: Iterable[SourceType] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        # ``source_types`` may be a one-shot iterable and both passes need it.
        types = None if source_types is None else tuple(source_types)

        if not self.semantic_enabled(min_score=min_score):
            return self._lexical.search(
                query,
                top_k=top_k,
                repositories=repositories,
                source_types=types,
                min_score=min_score,
            )

        # Candidates come from the lexical retriever, so repository and
        # source-type scope is enforced in exactly one place. The semantic
        # pass can only reorder what the filters already admitted; it can
        # never widen access.
        candidates = self._lexical.search(
            query,
            top_k=top_k * self._candidate_multiplier,
            repositories=repositories,
            source_types=types,
            min_score=0.0,
        )
        if not candidates:
            return []

        # Encode the query, plus only the passages this process has not seen
        # before. One batched call either way, so a cold cache costs exactly
        # what the uncached version cost and a warm one costs the query alone.
        wanted = [c.content for c in candidates]
        with self._vector_lock:
            missing = list(
                dict.fromkeys(t for t in wanted if t not in self._vectors)
            )
        try:
            vectors = self._backend.encode([query] + missing)
        except Exception:  # noqa: BLE001 - ranking must not become an outage
            return candidates[:top_k]
        if len(vectors) != len(missing) + 1:
            # A backend that returns the wrong shape is a broken backend, not
            # a reason to serve nothing.
            return candidates[:top_k]

        query_vector = vectors[0]
        fresh = dict(zip(missing, vectors[1:]))
        # Outside the lock: this is arithmetic on vectors nobody else holds
        # yet, and the lock covers dictionary work only.
        fresh_norms = {text: vector_norm(vector) for text, vector in fresh.items()}
        with self._vector_lock:
            if missing:
                if len(self._vectors) + len(missing) > self._vector_cache_max:
                    self._vectors.clear()
                    self._norms.clear()
                self._vectors.update(fresh)
                self._norms.update(fresh_norms)
            try:
                chunk_vectors = [
                    self._vectors[text] if text in self._vectors else fresh[text]
                    for text in wanted
                ]
                chunk_norms = [
                    self._norms[text] if text in self._norms else fresh_norms[text]
                    for text in wanted
                ]
            except KeyError:  # noqa: PERF203 - a racing clear is not fatal
                return candidates[:top_k]
        semantic_order = self._semantic_order(
            query_vector, chunk_vectors, chunk_norms
        )

        fused = self._fuse(len(candidates), semantic_order)
        ordered = sorted(range(len(candidates)), key=lambda i: (-fused[i], i))
        # Scores stay in lexical units. Callers and stored baselines read
        # these numbers, and a fused score would look like the same quantity
        # while meaning something else.
        return [candidates[i] for i in ordered[:top_k]]

    # ------------------------------------------------------------------
    def _semantic_order(
        self,
        query_vector: Sequence[float],
        chunk_vectors: Sequence[Sequence[float]],
        chunk_norms: Sequence[float],
    ) -> list[int]:
        """Candidate indices, most similar first.

        A named step rather than an expression inside ``search`` so that a
        test can rank the same candidates with the plain :func:`cosine` and
        compare the two orders. Without the seam, an error that pairs a chunk
        with another chunk's length passes every check that looks at one
        number at a time - which the first draft of the test for this did.
        """

        # The query's length, once for the whole ranking rather than once per
        # candidate; each chunk's came with its vector out of the memo.
        query_norm = vector_norm(query_vector)
        return sorted(
            range(len(chunk_vectors)),
            key=lambda i: cosine_with_norms(
                query_vector, query_norm, chunk_vectors[i], chunk_norms[i]
            ),
            reverse=True,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _fuse(count: int, semantic_order: Sequence[int]) -> list[float]:
        """Reciprocal rank fusion of the lexical order with a semantic order.

        Rank-based rather than score-based because BM25 scores and cosine
        similarities have no common scale; normalizing them against each
        other would invent a comparison neither one supports.
        """

        scores = [0.0] * count
        for lexical_rank, index in enumerate(range(count)):
            scores[index] += 1.0 / (RRF_K + lexical_rank + 1)
        for semantic_rank, index in enumerate(semantic_order):
            scores[index] += 1.0 / (RRF_K + semantic_rank + 1)
        return scores


class SentenceTransformerBackend(EmbeddingBackend):
    """A local sentence-transformers model, loaded from a path on disk.

    **It never downloads.** The path is required and is used as-is; there is
    no model name that would send the process to a hub on first use. A
    self-hosted assistant that fetches weights when it starts is a
    self-hosted assistant that phones out, and the whole point of this
    project is that it does not. Provision the directory out of band::

        python -c "from sentence_transformers import SentenceTransformer; \\
            SentenceTransformer('<name>').save('/srv/sidra/model')"
        export SIDRA_EMBEDDING_MODEL_PATH=/srv/sidra/model

    The import is deferred to first use so that this module - and therefore
    the retrieval package, and therefore the API - imports on a machine with
    no torch installed. ``available()`` answers that question honestly
    instead of raising it at startup.
    """

    name = "sentence-transformers"

    def __init__(
        self,
        model_path: str | os.PathLike[str],
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
    ) -> None:
        self._model_path = Path(model_path) if model_path else None
        self._model: object | None = None
        self._unavailable_reason = ""
        # Retrieval-tuned models are asymmetric: they are trained with one
        # marker on the question and another on the text being searched, and
        # encoding both the same way throws that training away. e5 wants
        # "query: " and "passage: ". Left empty for symmetric models, because
        # guessing the convention from a directory name would break the
        # moment somebody renames the directory.
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix
        #: Loading is check-then-act - "no model yet" then "build one" - and
        #: the server answers from a thread pool, so two first questions could
        #: each start their own load. On the machine this is aimed at that
        #: means two copies of the weights in a 6 GB card at once, next to a
        #: language model that is already most of it. Wasteful anywhere,
        #: out-of-memory there.
        self._load_lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def unavailable_reason(self) -> str:
        """Why the backend is not usable. Never a stack trace, never a path."""

        return self._unavailable_reason

    def available(self) -> bool:
        # Read first without the lock: once loaded this is the hot path and
        # the answer never goes back to False.
        if self._model is not None:
            return True
        with self._load_lock:
            return self._load_locked()

    def _load_locked(self) -> bool:
        if self._model is not None:
            # Another thread finished while this one waited.
            return True
        if self._model_path is None:
            self._unavailable_reason = "no model path configured"
            return False
        if not self._model_path.is_dir():
            self._unavailable_reason = "model path is not a directory"
            return False
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # noqa: BLE001 - absent or broken is the same
            self._unavailable_reason = f"sentence-transformers unusable: {type(exc).__name__}"
            return False
        try:
            # local_files_only keeps a mistyped path from becoming a download.
            self._model = SentenceTransformer(
                str(self._model_path), local_files_only=True
            )
        except Exception as exc:  # noqa: BLE001
            self._unavailable_reason = f"model did not load: {type(exc).__name__}"
            return False
        self._unavailable_reason = ""
        return True

    def encode(self, texts: Sequence[str]) -> list[Sequence[float]]:
        """Encode ``texts``; by this interface's contract ``texts[0]`` is the query."""

        if not self.available():
            raise RuntimeError(self._unavailable_reason or "embedding backend unavailable")
        if not texts:
            return []
        tagged = [self._query_prefix + texts[0]] + [
            self._passage_prefix + t for t in texts[1:]
        ]
        vectors = self._model.encode(tagged)  # type: ignore[union-attr]
        return [list(map(float, v)) for v in vectors]


def backend_from_settings(settings=None) -> EmbeddingBackend:
    """Build the configured backend, defaulting to none.

    Absence is the default and is not an error: the service runs without
    weights, more slowly at finding paraphrases, and that is a supported
    deployment rather than a broken one.
    """

    if settings is None:
        from sidra_ai.config.settings import get_settings

        settings = get_settings()
    path = getattr(settings, "embedding_model_path", "")
    if not path:
        return NoEmbeddingBackend()
    return SentenceTransformerBackend(
        path,
        query_prefix=getattr(settings, "embedding_query_prefix", ""),
        passage_prefix=getattr(settings, "embedding_passage_prefix", ""),
    )


def build_retriever(settings, store) -> Retriever:
    """The one place that decides which retriever the product runs.

    Ranking configuration was previously decided implicitly, by whichever
    caller happened to construct a retriever - the service used plain BM25
    while ``SIDRA_EMBEDDING_MODEL_PATH`` sat unread in settings, so the
    approved semantic pass was unreachable in the actual product. Routing
    every constructor through here means the service and the measurement
    scripts cannot quietly rank differently: a number measured elsewhere is
    a number about this exact configuration.

    With no model path configured this returns plain BM25 - not an
    ``EmbeddingRetriever`` wrapping an absent backend - so the no-weights
    configuration stays byte-for-byte the code path it always was.

    ``settings`` is duck-typed (``embedding_model_path`` and the two prefix
    fields) so the scripts can pass a plain namespace without importing the
    full Settings machinery.
    """

    from sidra_ai.retrieval.candidates import Fts5CandidateSource
    from sidra_ai.retrieval.search import BM25Retriever

    # FTS5 shortlists which chunks BM25 scores on an unfiltered search; BM25
    # still does all the scoring, so the k1=1.5 this corpus was tuned to and
    # the filter-scoped statistics both survive. Measured on the real 3,761
    # chunk corpus: the judge's top-5 is identical to a full scan on every one
    # of its 40 questions from a pool of 25 upward, and the product's pool is
    # 200. Search 14.8ms -> 3.6ms. The way back is one argument: construct
    # ``BM25Retriever(store)`` with no candidate source and the full scan is
    # what runs. See scripts/measure_fts5_candidates.py for the curve.
    lexical = BM25Retriever(store, candidate_source=Fts5CandidateSource())
    model_path = getattr(settings, "embedding_model_path", "") or ""
    if not model_path:
        return lexical
    backend = SentenceTransformerBackend(
        model_path,
        query_prefix=getattr(settings, "embedding_query_prefix", "") or "",
        passage_prefix=getattr(settings, "embedding_passage_prefix", "") or "",
    )
    return EmbeddingRetriever(lexical, backend)
