"""Narrowing *which* chunks BM25 scores, without touching *how* it scores them.

C-1464 measured the whole-hog swap: replacing this project's BM25 with
SQLite FTS5 made search 68x faster and lost an answer (``answered`` 14->13,
MRR 0.284->0.272). The cause was not the index, it was the scoring - FTS5's
``bm25()`` is fixed at k1=1.2 where this corpus was tuned to **k1=1.5**, and
its statistics are whole-table where the retriever scopes them to the filter.

This module keeps the scoring and borrows only the part FTS5 is unambiguously
better at: deciding, quickly, which chunks are worth looking at. A candidate
source answers one question - *which positions contain at least one query
term* - and is allowed to answer "I don't know" (``None``), in which case the
retriever scans everything exactly as before.

Why that is safe to do at all rests on one property of the scorer, and only
holds where the property holds:

    For an **unfiltered** search, BM25's IDF and average-length statistics are
    the whole-corpus ones, which are already precomputed. Restricting the
    scoring loop to a subset of positions therefore leaves each scored chunk's
    score *bit-identical*. The result changes only if a chunk that belonged in
    the top-k was never offered as a candidate.

For a **filtered** search the statistics are recomputed over the eligible
chunks, which requires walking them - so there is nothing to save and the
retriever does not ask. That is a deliberate scope limit, not an oversight:
a candidate set cannot supply corpus statistics it was selected out of.

So the whole question is recall of the candidate set, and it is an empirical
one - see ``scripts/measure_fts5_candidates.py`` for the measured curve of
candidate count against the 38-question judge.

**One difference from a full scan is not a recall problem and does not go
away with a bigger pool.** BM25 breaks exact score ties by chunk id; a
shortlist that cuts through a run of *exactly equal* scores offers a
different equal-scoring subset to break ties among, so the tail of the result
can name different chunks - at identical scores. Retrieval stays
deterministic (the same corpus and query give the same answer every time),
and no chunk is displaced by a worse-scoring one, but "identical to the full
scan" is a promise this makes about **scores and the order of distinct
scores**, not about which of several indistinguishable chunks it hands back.
On the real 3,761-chunk corpus this never fired: all 40 judge questions
returned the byte-identical top-5 from a pool of 25 upward.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Iterable, Sequence

from sidra_ai.retrieval.search import tokenize


class CandidateSource:
    """What a candidate generator must do.

    Two rules make a candidate source safe to plug in.

    **Extra candidates are free; missing ones are not.** Every position handed
    back is scored by the real BM25 and has to win on that score, so a
    generator that is too generous costs only time. A generator that omits a
    chunk which would have placed removes it from the answer - silently. A
    generator that is unsure must therefore return ``None`` (scan everything)
    rather than a partial list.

    **It may decline.** ``None`` from either method means "no opinion", and the
    retriever falls back to its full scan. This is the way back: a broken,
    unavailable or unbuilt candidate source degrades to the behaviour that
    shipped, not to a worse answer.
    """

    def reindex(self, token_lists: Iterable[Sequence[str]]) -> None:
        """Rebuild from already-tokenized chunks, in the retriever's own order.

        Tokens rather than chunks, because the retriever has just tokenized
        every chunk to build its own postings and tokenization is the whole
        cost of building this index - measured at 1.24s against 1.65s for the
        retriever itself on the real corpus. Handing over the work already
        done makes the candidate index nearly free instead of a 75% tax on
        first-index time.
        """
        raise NotImplementedError

    def extend(self, token_lists: Iterable[Sequence[str]]) -> bool:
        """Append newly indexed chunks, or return ``False`` to decline.

        A store that only grows - which is what ingestion does - should not
        make its index start over. Declining is always safe: the retriever
        falls back to re-tokenizing everything and calling :meth:`reindex`,
        which is what happened before this existed. The positions appended
        must continue the retriever's own numbering, so a source that cannot
        guarantee that must decline rather than guess.
        """

        return False

    def positions(self, query_terms: Sequence[str], *, limit: int) -> list[int] | None:
        """Positions worth scoring, best first, or ``None`` to decline."""
        raise NotImplementedError


def fts5_available() -> bool:
    """Whether this interpreter's SQLite was built with the FTS5 extension.

    FTS5 is a compile-time option. It is present in CPython's bundled SQLite on
    every platform this project targets, but "usually present" is not a thing
    to assume in a code path that decides which evidence a user sees, so the
    check is a real one and the answer is allowed to be no.
    """

    try:
        db = sqlite3.connect(":memory:")
    except sqlite3.Error:  # pragma: no cover - sqlite3 without :memory:
        return False
    try:
        db.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
    except sqlite3.Error:
        return False
    finally:
        db.close()
    return True


class Fts5CandidateSource(CandidateSource):
    """SQLite FTS5 used as a shortlist, never as a ranking.

    The index holds this project's **own** tokens - ``" ".join(tokenize(...))``
    - so every measured decision in :func:`~sidra_ai.retrieval.search.tokenize`
    (CJK bigrams, the kana-only rule, the interrogative rule, the stopwords)
    decides what is searchable here too. FTS5's tokenizer then only has to
    split on whitespace, and its ``bm25()`` is used for one purpose: putting
    the most promising candidates first so that a ``LIMIT`` cuts in a sensible
    place. Its scores are discarded.
    """

    #: The index is built where the store is loaded and queried where requests
    #: are served, and in this product those are different threads: the API
    #: builds it during startup and answers on Starlette's worker threads.
    #: ``check_same_thread=False`` alone is not enough - it removes the
    #: affinity check without making concurrent use of one connection safe,
    #: and whether that is safe depends on how the local SQLite was compiled.
    #: A lock decides it here instead of depending on the build. It serializes
    #: a query measured at ~1ms against the 15ms full scan it replaces, so the
    #: contended case is still faster than not having the shortlist at all.
    def __init__(self, token_lists: Iterable[Sequence[str]] = ()) -> None:
        self._db: sqlite3.Connection | None = None
        self._count = 0
        self._lock = threading.Lock()
        self.reindex(token_lists)

    @classmethod
    def from_chunks(cls, chunks: Iterable) -> "Fts5CandidateSource":
        """Build from chunks, tokenizing them. For callers with no postings."""

        return cls([tokenize(chunk.content) for chunk in chunks])

    # ------------------------------------------------------------------
    def reindex(self, token_lists: Iterable[Sequence[str]]) -> None:
        with self._lock:
            self._replace(token_lists)

    def _replace(self, token_lists: Iterable[Sequence[str]]) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._count = 0
        try:
            db = sqlite3.connect(":memory:", check_same_thread=False)
            db.execute(
                "CREATE VIRTUAL TABLE chunks USING fts5"
                "(body, tokenize='unicode61 remove_diacritics 0')"
            )
            count = 0
            rows = []
            for tokens in token_lists:
                count += 1
                rows.append((count, " ".join(tokens)))
            db.executemany("INSERT INTO chunks(rowid, body) VALUES (?, ?)", rows)
        except sqlite3.Error:
            # No FTS5, or the build failed part-way. Decline from here on
            # rather than answer from a half-filled index.
            self._db = None
            return
        self._count = count
        self._db = db

    def extend(self, token_lists: Iterable[Sequence[str]]) -> bool:
        """Insert new rows after the last one, keeping rowid == position + 1.

        The whole point: an ingestion that adds one document used to make the
        next query rebuild this table from every chunk in the store. Measured
        while ingesting and serving at the same time, one query after 204
        documents took 1.66 s where the first took 1.5 ms.
        """

        rows = []
        with self._lock:
            if self._db is None:
                return False
            count = self._count
            for tokens in token_lists:
                count += 1
                rows.append((count, " ".join(tokens)))
            if not rows:
                return True
            try:
                self._db.executemany(
                    "INSERT INTO chunks(rowid, body) VALUES (?, ?)", rows
                )
            except sqlite3.Error:
                # A half-applied append is worse than none: drop the index so
                # `positions` declines and the retriever scans everything,
                # rather than answering from a table missing rows nobody knows
                # about.
                self._db.close()
                self._db = None
                self._count = 0
                return False
            self._count = count
            return True

    # ------------------------------------------------------------------
    @staticmethod
    def _match_expression(query_terms: Iterable[str]) -> str:
        """An OR of phrase-quoted terms.

        Quoting is what makes a term with a separator in it - ``top_k``, which
        ``unicode61`` splits at the underscore - match as the adjacent pair it
        was indexed as, instead of failing to parse. It can also match a
        coincidentally adjacent pair from two different source tokens, which is
        an extra candidate, and extra candidates are free.
        """

        return " OR ".join(
            '"' + term.replace('"', "") + '"' for term in query_terms
        )

    def positions(self, query_terms: Sequence[str], *, limit: int) -> list[int] | None:
        if not query_terms or limit <= 0:
            return None
        with self._lock:
            if self._db is None:
                return None
            if limit >= self._count:
                # Asking for everything: the full scan is already the answer,
                # and going through FTS5 to say so would only cost time.
                return None
            try:
                rows = self._db.execute(
                    "SELECT rowid FROM chunks WHERE chunks MATCH ? "
                    "ORDER BY bm25(chunks) LIMIT ?",
                    (self._match_expression(query_terms), limit),
                ).fetchall()
            except sqlite3.Error:
                # A term the MATCH grammar rejects must not become "no results".
                return None
        return [rowid - 1 for (rowid,) in rows]
