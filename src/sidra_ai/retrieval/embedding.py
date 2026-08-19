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
        candidate_multiplier: int = 10,
    ) -> None:
        self._lexical = lexical
        self._backend = backend or NoEmbeddingBackend()
        #: How far down the lexical list to look for chunks the semantic pass
        #: can promote. Bounded because encoding is the expensive half.
        #: Measured over the 26-question set on the five repositories:
        #: 10, 20, 40 and 80 all answer the same 13 questions, so the window
        #: buys nothing past 50 chunks - the misses are either outside any
        #: window lexically or ones the model demotes when it does see them.
        #: What widening does move is discrimination, downward (+30.8pt at
        #: 10 and 20, +26.9 at 40, +23.1 at 80): a bigger window feeds the
        #: reranker more plausible-looking foreign chunks. 10 keeps the best
        #: discrimination, the best measured MRR (0.436 against 0.429 at 20),
        #: and half the encoding cost of 20.
        self._candidate_multiplier = max(1, candidate_multiplier)

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

        try:
            vectors = self._backend.encode([query] + [c.content for c in candidates])
        except Exception:  # noqa: BLE001 - ranking must not become an outage
            return candidates[:top_k]
        if len(vectors) != len(candidates) + 1:
            # A backend that returns the wrong shape is a broken backend, not
            # a reason to serve nothing.
            return candidates[:top_k]

        query_vector, chunk_vectors = vectors[0], vectors[1:]
        semantic_order = sorted(
            range(len(candidates)),
            key=lambda i: cosine(query_vector, chunk_vectors[i]),
            reverse=True,
        )

        fused = self._fuse(len(candidates), semantic_order)
        ordered = sorted(range(len(candidates)), key=lambda i: (-fused[i], i))
        # Scores stay in lexical units. Callers and stored baselines read
        # these numbers, and a fused score would look like the same quantity
        # while meaning something else.
        return [candidates[i] for i in ordered[:top_k]]

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

    # ------------------------------------------------------------------
    @property
    def unavailable_reason(self) -> str:
        """Why the backend is not usable. Never a stack trace, never a path."""

        return self._unavailable_reason

    def available(self) -> bool:
        if self._model is not None:
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

    from sidra_ai.retrieval.search import BM25Retriever

    lexical = BM25Retriever(store)
    model_path = getattr(settings, "embedding_model_path", "") or ""
    if not model_path:
        return lexical
    backend = SentenceTransformerBackend(
        model_path,
        query_prefix=getattr(settings, "embedding_query_prefix", "") or "",
        passage_prefix=getattr(settings, "embedding_passage_prefix", "") or "",
    )
    return EmbeddingRetriever(lexical, backend)
