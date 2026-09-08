"""Two questions arriving together must not corrupt the index between them.

The chat route is a synchronous FastAPI endpoint, so the server answers from
a thread pool: two questions arriving at once are two threads inside the same
retriever. The index build had no lock, and it does not merely read - it
resets the postings and then fills them. Two threads interleaving there leave
postings that do not line up with the chunks, and positions index into both.

Measured before the fix, eight threads on a fresh 9,849-chunk index, six
attempts out of six: 77,999 postings against 9,849 chunks. Nothing raised.
The searches returned answers. They were just answers derived from whichever
chunk happened to sit at the position the scorer asked for - the failure mode
that looks like working software.

These tests are timing-dependent by nature, so they are written to fail loudly
when the invariant breaks rather than to prove it can never break: the
structural check (postings line up with chunks) holds deterministically
whatever the interleaving, which is the property the lock actually buys.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.documents import (  # noqa: E402
    Document,
    Provenance,
    SourceType,
    TrustLevel,
)
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

_REPO = "owner/alpha"
_THREADS = 8


def _store(documents: int) -> DocumentStore:
    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    for i in range(documents):
        store.add(
            Document(
                # Long enough to split into several chunks, so a build is not
                # over before a second thread can enter it.
                content=(
                    f"第 {i} 章。競合の分析と収益化の方針について書いた文書。"
                    + "掲載順は売らないという約束を繰り返し確認する。" * 40
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


def _ask_together(retriever: BM25Retriever, query: str) -> tuple[list, list]:
    answers: list[list[str]] = []
    errors: list[str] = []
    ready = threading.Barrier(_THREADS)

    def ask() -> None:
        try:
            ready.wait(timeout=10)
            answers.append(
                [r.chunk.chunk_id for r in retriever.search(query, top_k=5)]
            )
        except Exception as exc:  # noqa: BLE001 - the failure is the finding
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=ask) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return answers, errors


def test_a_first_index_built_by_several_threads_stays_consistent() -> None:
    store = _store(40)
    retriever = BM25Retriever(store)

    answers, errors = _ask_together(retriever, "収益化の方針")

    assert not errors
    assert len(retriever._term_frequencies) == len(retriever._chunks)
    assert len(retriever._lengths) == len(retriever._chunks)
    assert answers and all(a == answers[0] for a in answers)


def test_ingesting_while_several_threads_ask_stays_consistent() -> None:
    """The live shape: background ingestion adds while questions arrive."""

    store = _store(24)
    retriever = BM25Retriever(store)
    retriever.search("収益化の方針", top_k=5)

    stop = threading.Event()
    added = {"n": 0}

    def ingest() -> None:
        i = 100
        while not stop.is_set() and added["n"] < 20:
            store.add(
                Document(
                    content=f"後から足した第 {i} 章。審査の基準について。" * 20,
                    provenance=Provenance(
                        source="github",
                        repository=_REPO,
                        path=f"docs/late{i}.md",
                        commit_sha="0" * 40,
                        timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                        source_type=SourceType.DOCS,
                        trust_level=TrustLevel.INTERNAL_REPO,
                        license="proprietary",
                    ),
                )
            )
            added["n"] += 1
            i += 1

    writer = threading.Thread(target=ingest)
    writer.start()
    try:
        _, errors = _ask_together(retriever, "審査の基準")
    finally:
        stop.set()
        writer.join(timeout=30)

    assert not errors
    assert len(retriever._term_frequencies) == len(retriever._chunks)
    assert len(retriever._lengths) == len(retriever._chunks)
    # And the index describes the store it was built from, whatever order
    # the adds and the searches happened to interleave in.
    retriever.search("審査の基準", top_k=5)
    assert len(retriever._chunks) == len(tuple(store.chunks()))


def test_the_postings_still_line_up_after_concurrent_filtered_searches() -> None:
    """Filtered search writes a memo too; two threads must not tear it."""

    store = _store(30)
    retriever = BM25Retriever(store)

    errors: list[str] = []
    ready = threading.Barrier(_THREADS)

    def ask(index: int) -> None:
        try:
            ready.wait(timeout=10)
            retriever.search(
                "競合", top_k=5, repositories=[_REPO, f"owner/ghost{index}"]
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=ask, args=(i,)) for i in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors
    assert len(retriever._term_frequencies) == len(retriever._chunks)
    for positions, _frequency, _length in retriever._filter_cache.values():
        assert all(p < len(retriever._chunks) for p in positions)
