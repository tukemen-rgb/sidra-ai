"""Lexical retrieval over indexed chunks.

v0.1 uses BM25 in pure Python rather than embeddings. Three reasons: it has
no dependencies, it is fully deterministic (so evals are stable), and it
needs no model to be running - which keeps the "works with no weights
installed" promise. Embedding-based retrieval slots in behind the same
:class:`Retriever` interface when a local embedding model is available.

Tokenization handles Japanese without a morphological analyzer by emitting
character bigrams for CJK runs, which is a well-worn approximation for
mixed-language corpora. Compatibility-equivalent Unicode is normalized before
tokenization so full-width ASCII and half-width katakana do not silently miss
the same repository content written in their common forms.
"""

from __future__ import annotations

import abc
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

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

#: Hiragana-only bigrams are grammar, not subject - and BM25 cannot tell the
#: difference by itself. IDF rewards rarity, but an unusual particle
#: collocation is *lexically* rare while carrying no topic at all, so the
#: formula hands it a high weight for the wrong reason. Measured on the real
#: 484-document corpus: ``はど`` scored IDF **4.30** against **3.69** for
#: ``競合`` - the shape of the question outweighed what it was about.
#:
#: The failure that came from it: one interview questionnaire took first place
#: for a quarter of a 20-question set - competitors, monetisation, moderation,
#: privacy, the 90-day plan - matching on ``どこ``/``こで``/``すか`` while the
#: content word appeared **zero times** in the winning chunk.
#:
#: Dropping them costs the rare hiragana-only content word (ひとり, たくさん).
#: That trade was measured rather than assumed, against the alternative of
#: keeping such terms and holding down only the chunks that matched nothing
#: else - see docs/OUTCOMES.md for the four-way comparison. Removal scored
#: higher on every number of the 38-question judge, and the judge is what
#: holds this decision honest rather than this comment.
_KANA_ONLY = re.compile(r"^[぀-ゟ]+$")

#: Interrogatives carry the question's form, never its subject. They are
#: kanji, so the hiragana rule above does not reach them, and they are rare
#: enough to score high on their own: ``何で`` measured IDF **6.37**, the
#: largest of any term in the queries that failed.
_INTERROGATIVE = frozenset("何誰")


def _is_grammar_only(token: str) -> bool:
    """Whether a CJK token says how a sentence is built, not what it is about."""

    return bool(_KANA_ONLY.match(token)) or any(c in _INTERROGATIVE for c in token)


#: Adjacent chunks from one long document often repeat the same evidence due
#: to chunk overlap. Prefer breadth before allowing one document to consume
#: the whole context window, while still permitting two chunks when a section
#: boundary splits a useful passage.
_MAX_CHUNKS_PER_DOCUMENT = 2

#: The private API accepts long natural-language queries. Without a scoring
#: bound, one request can contain thousands of distinct tokens and multiply
#: per-chunk BM25 work even though only a small evidence set is returned.
#: Keep the most discriminative corpus-present terms and bound the inner loop.
_MAX_SCORING_QUERY_TERMS = 128


def tokenize(text: str) -> list[str]:
    """NFKC-normalized, case-folded Latin words plus CJK character bigrams."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = [t for t in _LATIN.findall(normalized) if t not in _STOPWORDS]

    for run in _CJK_RUN.findall(normalized):
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))

    return [
        t for t in tokens if t not in _STOPWORDS and not _is_grammar_only(t)
    ]


#: Any hiragana character inside a token marks it as glue for the purposes of
#: :func:`subject_terms`. The kana-only rule above already removes tokens that
#: are *entirely* grammar; what it cannot remove is the bigram that straddles
#: a particle boundary - ``の天``/``気は`` out of ``明日の天気は`` - because
#: those mix kanji in. They stay in scoring (dropping them was not measured),
#: but they must not count as proof that a chunk is about the question.
_HIRAGANA_ANY = re.compile(r"[぀-ゟ]")


def subject_terms(query: str) -> tuple[str, ...]:
    """Query tokens that name the question's subject rather than its grammar.

    Latin words, katakana and pure-kanji bigrams qualify; anything containing
    hiragana is treated as sentence glue. ``天気を教えて`` keeps ``天気`` and
    drops ``を教``/``教え`` - which is exactly the split BM25 cannot make,
    because a rare particle collocation is lexically rare while carrying no
    topic (see the ``_KANA_ONLY`` note above for the measured failure).
    """

    return tuple(
        term
        for term in dict.fromkeys(tokenize(query))
        if not _HIRAGANA_ANY.search(term)
    )


def evidence_mentions_subject(query: str, chunks: Iterable[Chunk]) -> bool:
    """Whether any chunk shares at least one subject term with the query.

    This is the honesty floor for answer composition, not a ranking change:
    when every retrieved chunk matched only cross-word glue bigrams, the
    "evidence" is about the shape of the sentence, and composing a cited
    answer from it presents unrelated material as fact. A query with no
    subject terms at all cannot be judged and returns True, leaving the
    existing behavior untouched.
    """

    wanted = set(subject_terms(query))
    if not wanted:
        return True
    return any(wanted.intersection(tokenize(chunk.content)) for chunk in chunks)


def _bounded_query_terms(
    query_terms: Sequence[str],
    document_frequency: Mapping[str, int],
) -> tuple[str, ...]:
    """Return a bounded, discriminative set of corpus-present query terms.

    Query terms absent from the active retrieval corpus cannot affect BM25 and
    are removed before scoring. If more than the hard scoring budget remain,
    prefer rarer terms (lower document frequency means higher BM25 IDF), while
    preserving original query order among terms with equal frequency. This
    prevents one valid but very large request from turning BM25's inner loop
    into unbounded ``chunks × unique-query-terms`` work without blindly
    truncating away a rare term that appears near the end of a natural query.
    """

    present = [term for term in query_terms if document_frequency.get(term, 0) > 0]
    if len(present) <= _MAX_SCORING_QUERY_TERMS:
        return tuple(present)

    ranked_positions = sorted(
        range(len(present)),
        key=lambda position: (document_frequency[present[position]], position),
    )[:_MAX_SCORING_QUERY_TERMS]
    selected_positions = set(ranked_positions)
    return tuple(
        term for position, term in enumerate(present) if position in selected_positions
    )


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


def _diversify_results(scored: Sequence[SearchResult], top_k: int) -> list[SearchResult]:
    """Prefer source breadth, then limited depth, while preserving score order.

    A single "at most two chunks per document" pass still lets the two highest
    scoring chunks from one document consume ``top_k=2`` before a relevant peer
    is considered.  Diversification therefore happens in three deterministic
    stages:

    1. take the highest-scoring chunk from each distinct document;
    2. if space remains, allow a second chunk per document;
    3. if the corpus is too narrow to fill ``top_k``, backfill remaining chunks.

    Every stage preserves the original BM25 ordering among eligible chunks.
    This keeps small context windows diverse without reducing result count for
    single-document queries.
    """

    if top_k <= 0:
        return []

    selected: list[SearchResult] = []
    selected_chunk_ids: set[str] = set()
    per_document: Counter[str] = Counter()

    # Breadth first: one chunk per document. This is the critical pass for
    # small context windows such as top_k=2.
    for result in scored:
        document_id = result.chunk.document_id
        if per_document[document_id]:
            continue
        selected.append(result)
        selected_chunk_ids.add(result.chunk.chunk_id)
        per_document[document_id] += 1
        if len(selected) >= top_k:
            return selected

    # Depth second: allow one additional chunk from each document while
    # keeping the original score order.
    for result in scored:
        if result.chunk.chunk_id in selected_chunk_ids:
            continue
        document_id = result.chunk.document_id
        if per_document[document_id] >= _MAX_CHUNKS_PER_DOCUMENT:
            continue
        selected.append(result)
        selected_chunk_ids.add(result.chunk.chunk_id)
        per_document[document_id] += 1
        if len(selected) >= top_k:
            return selected

    # Narrow-corpus fallback: do not return fewer than top_k merely because
    # only one or two documents matched.
    for result in scored:
        if result.chunk.chunk_id in selected_chunk_ids:
            continue
        selected.append(result)
        selected_chunk_ids.add(result.chunk.chunk_id)
        if len(selected) >= top_k:
            break
    return selected


class BM25Retriever:
    """Okapi BM25 over the chunks currently in a :class:`DocumentStore`.

    The index is rebuilt lazily whenever the store's chunk count changes.
    For a corpus of a few thousand chunks this is cheaper and far simpler
    than maintaining incremental postings.

    Repository/source-type filters define a retrieval corpus, not merely a
    post-score visibility mask. IDF and average document length are therefore
    recomputed over the eligible chunks for each filtered search. This keeps a
    repository-scoped query invariant when unrelated repositories are added to
    the shared store, and prevents cross-repository corpus statistics from
    silently changing ranking or score thresholds.

    ``None`` means "no scope restriction". An explicitly empty repository or
    source-type sequence means "search nothing" rather than broadening back to
    the whole store. This fail-closed distinction matters at API boundaries
    where callers may intentionally resolve an authorization scope to zero
    repositories.

    Query-side term frequency is deliberately saturated at one in v0.1. The
    scorer has no BM25 ``k3``/query-frequency term, so summing the same token
    repeatedly would let keyword stuffing linearly inflate an evidence score
    and potentially cross a downstream ``min_score`` threshold without adding
    any new lexical evidence.

    Distinct query terms are also bounded before the per-chunk scoring loop.
    Only corpus-present terms can contribute, and when the request contains
    more than the scoring budget, the rarest terms are retained first. This
    keeps a 32k-character API query from becoming a per-request CPU amplifier
    while preserving the most discriminative lexical evidence.
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

    @staticmethod
    def _idf_for_counts(total: int, frequency: int) -> float:
        if total == 0 or frequency == 0:
            return 0.0
        return math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

    def _idf(self, term: str) -> float:
        """Return whole-store IDF for compatibility with unfiltered callers/tests."""

        return self._idf_for_counts(
            len(self._chunks), self._document_frequency.get(term, 0)
        )

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
        """Return score-ranked chunks with filter-scoped BM25 statistics."""

        self._ensure_index()
        query_terms = tuple(dict.fromkeys(tokenize(query)))
        if not query_terms or not self._chunks or top_k <= 0:
            return []

        repository_filter = (
            None if repositories is None else {r.lower() for r in repositories}
        )
        type_filter = None if source_types is None else set(source_types)

        eligible_positions: list[int] = []
        for position, chunk in enumerate(self._chunks):
            provenance = chunk.provenance
            if (
                repository_filter is not None
                and provenance.repository.lower() not in repository_filter
            ):
                continue
            if type_filter is not None and provenance.source_type not in type_filter:
                continue
            eligible_positions.append(position)

        if not eligible_positions:
            return []

        # A filtered search is its own BM25 corpus. Computing IDF/length
        # statistics from excluded repositories lets unrelated data change a
        # scoped query's score and can flip ranking or min_score decisions.
        filtered_document_frequency: Counter[str] = Counter()
        filtered_total_length = 0
        for position in eligible_positions:
            filtered_document_frequency.update(self._term_frequencies[position].keys())
            filtered_total_length += self._lengths[position]

        filtered_total = len(eligible_positions)
        filtered_average_length = filtered_total_length / filtered_total
        query_terms = _bounded_query_terms(query_terms, filtered_document_frequency)
        if not query_terms:
            return []

        scored: list[SearchResult] = []
        for position in eligible_positions:
            chunk = self._chunks[position]
            counts = self._term_frequencies[position]
            length = self._lengths[position] or 1
            score = 0.0
            for term in query_terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1
                    - self.b
                    + self.b * length / (filtered_average_length or 1)
                )
                idf = self._idf_for_counts(
                    filtered_total, filtered_document_frequency.get(term, 0)
                )
                score += idf * (frequency * (self.k1 + 1)) / denominator

            if score > min_score:
                scored.append(SearchResult(chunk=chunk, score=score))

        scored.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        return _diversify_results(scored, top_k)


class Retriever(abc.ABC):
    """What every retrieval backend must provide.

    v0.1 ships one implementation, :class:`BM25Retriever`, chosen because it
    is deterministic and needs no model weights - evals stay stable and the
    service runs on a clean machine. The reason this is an abstract base
    rather than an alias for that one class is the swap it exists to allow:
    replacing lexical matching with a local embedding model, without the API
    or the service layer knowing.

    Two properties are load-bearing for anything that implements this.

    **Results carry provenance.** A retriever returns
    :class:`SearchResult` objects wrapping a
    :class:`~sidra_ai.documents.Chunk`, and the chunk keeps the full
    provenance of the document it came from. A backend that returns bare text
    breaks citation, which is the point of the system.

    **Filters are honoured, not approximated.** ``repositories`` and
    ``source_types`` are access scope, not ranking hints. Returning a chunk
    from outside the requested repositories is a scope violation regardless of
    how relevant it looked.
    """

    @abc.abstractmethod
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        repositories: Sequence[str] | None = None,
        source_types: Iterable[SourceType] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Return at most ``top_k`` results, most relevant first.

        Implementations must return an empty list rather than raising when the
        query is empty or nothing matches: "no evidence" is an answer the
        service knows how to report, an exception is not.
        """


Retriever.register(BM25Retriever)
