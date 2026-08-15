"""Lexical retrieval over indexed chunks.

v0.1 uses BM25 in pure Python rather than embeddings. Three reasons: it has
no dependencies, it is fully deterministic (so evals are stable), and it
needs no model to be running - which keeps the "works with no weights
installed" promise. Embedding-based retrieval slots in behind the same
:class:`Retriever` interface when a local embedding model is available.

Tokenization handles Japanese without a morphological analyzer by emitting
character bigrams for CJK runs, which is a well-worn approximation for
mixed-language corpora.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sidra_ai.documents import Chunk, SourceType
from sidra_ai.retrieval.store import DocumentStore

_LATIN = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[぀-ゟ゠-ヿ一-鿿]+")
_CJK_CHAR = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Common tokens that carry no retrieval signal in this corpus.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for",
        "on", "with", "as", "by", "at", "from", "this", "that", "it", "be",
        "した", "する", "して", "です", "ます", "こと", "ため", "この", "その",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercased Latin words plus CJK character bigrams."""

    lowered = text.lower()
    tokens = [t for t in _LATIN.findall(lowered) if t not in _STOPWORDS]

    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))

    return [t for t in tokens if t not in _STOPWORDS]


@dataclass(frozen=True)
class SearchResult:
    """A retrieved chunk with its score and full provenance."""

    chunk: Chunk
    score: float

    @property
    def content(self) -> str:
        return self.chunk.content

    @property
    def provenance(self):  # noqa: ANN201 - passthrough
        return self.chunk.provenance

    @property
    def redacted(self) -> bool:
        return self.chunk.redacted

    def to_dict(self) -> dict[str, Any]:
        return {"score": round(self.score, 4), **self.chunk.to_dict()}


class BM25Retriever:
    """Okapi BM25 over the chunks currently in a :class:`DocumentStore`.

    The index is rebuilt lazily whenever the store's chunk count changes.
    For a corpus of a few thousand chunks this is cheaper and far simpler
    than maintaining incremental postings.
    """

    def __init__(self, store: DocumentStore, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.store = store
        self.k1 = k1
        self.b = b
        self._chunks: tuple[Chunk, ...] = ()
        self._term_frequencies: list[Counter[str]] = []
        self._lengths: list[int] = []
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 0.0
        self._indexed_count = -1

    # ------------------------------------------------------------------
    def _ensure_index(self) -> None:
        chunks = tuple(self.store.chunks())
        if self._indexed_count == len(chunks) and self._chunks == chunks:
            return

        self._chunks = chunks
        self._term_frequencies = []
        self._lengths = []
        self._document_frequency = Counter()

        for chunk in chunks:
            tokens = tokenize(chunk.content)
            counts = Counter(tokens)
            self._term_frequencies.append(counts)
            self._lengths.append(len(tokens))
            self._document_frequency.update(counts.keys())

        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._indexed_count = len(chunks)

    def _idf(self, term: str) -> float:
        total = len(self._chunks)
        frequency = self._document_frequency.get(term, 0)
        if total == 0 or frequency == 0:
            return 0.0
        return math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

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
        """Return the best-scoring chunks, most relevant first."""

        self._ensure_index()
        query_terms = tokenize(query)
        if not query_terms or not self._chunks:
            return []

        repository_filter = {r.lower() for r in repositories} if repositories else None
        type_filter = set(source_types) if source_types else None

        scored: list[SearchResult] = []
        for position, chunk in enumerate(self._chunks):
            provenance = chunk.provenance
            if repository_filter and provenance.repository.lower() not in repository_filter:
                continue
            if type_filter and provenance.source_type not in type_filter:
                continue

            counts = self._term_frequencies[position]
            length = self._lengths[position] or 1
            score = 0.0
            for term in query_terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / (self._average_length or 1)
                )
                score += self._idf(term) * (frequency * (self.k1 + 1)) / denominator

            if score > min_score:
                scored.append(SearchResult(chunk=chunk, score=score))

        scored.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        return scored[:top_k]


#: The interface every retriever must satisfy. Kept as an alias so callers
#: depend on the concept, not the current implementation.
Retriever = BM25Retriever
