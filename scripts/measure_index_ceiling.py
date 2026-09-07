"""Where does today's index stop being comfortable? (C-1133)

The backlog has carried "sqlite + FTS5" since the beginning, on the
reasoning that the in-memory index has a ceiling. Nobody had measured
where. This does, because a vessel swap that cannot say what it raised is
a rewrite with a story attached.

Two costs are measured, both on the real thing:

* **the rebuild** - the first search after anything is added pays for the
  whole index, and every ``add`` invalidates it, and
* **the search** - the eligibility filter walks every chunk, so a query
  costs time proportional to the corpus.

The synthetic ladder shows the SHAPE; the real corpus gives the RATE, and
they are not the same number. Measured: the ladder costs about 7.5µs per
chunk and the real corpus about 19.4µs - the ladder is the *optimistic*
one, because its documents are short and its queries are two tokens, while
a real question is a sentence with many terms to score. The ladder was
written expecting the opposite (a shared vocabulary making every query
match everything) and the measurement said otherwise, which is why the
real corpus is measured beside it rather than extrapolated from it.

    python scripts/measure_index_ceiling.py            # ladder only
    python scripts/measure_index_ceiling.py <repo=path ...>   # and the corpus

Exit 0 always: this is a measurement, not a gate.
"""

from __future__ import annotations

import contextlib
import io
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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

REPOSITORY = "tukemen-rgb/sidra-ai"

#: What "uncomfortable" means, said out loud rather than left to taste: a
#: reply a person waits half a second for is a reply they notice waiting for.
SLOW_SEARCH_MS = 500.0

#: Plain prose. Nothing here may look like a credential - a corpus built for
#: a benchmark is still a corpus, and the gate is not the place to find out.
_WORDS = (
    "設計 判断 記録 索引 検索 生成 検証 実測 器 上限 文書 断片 質問 回答 "
    "the vessel holds documents and answers questions about them"
).split()

LADDER: tuple[int, ...] = (500, 1000, 2000, 4000, 8000)


def synthetic(index: int) -> Document:
    body = " ".join(_WORDS[(index + n) % len(_WORDS)] for n in range(120))
    return Document(
        content=f"# 文書 {index}\n\n{body}\n\n目印 marker-{index}。\n",
        provenance=Provenance(
            source="github",
            repository=REPOSITORY,
            path=f"docs/synthetic/{index:06d}.md",
            commit_sha=f"{index:040x}",
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="unknown",
        ),
    )


def _timed_searches(retriever, queries) -> float:
    start = time.time()
    for query in queries:
        retriever.search(query, top_k=5)
    return 1000 * (time.time() - start) / max(1, len(queries))


def ladder() -> list[dict]:
    gate = SecurityGate(GatePolicy(), allowed_repositories=[REPOSITORY])
    store = DocumentStore(gate)
    retriever = BM25Retriever(store)
    rows: list[dict] = []
    added = 0
    for size in LADDER:
        start = time.time()
        for index in range(added, size):
            store.add(synthetic(index))
        ingest_ms = 1000 * (time.time() - start) / max(1, size - added)
        added = size
        start = time.time()
        retriever.search("目印 marker-7", top_k=5)
        rebuild = time.time() - start
        each = _timed_searches(
            retriever, [f"目印 marker-{n * 13}" for n in range(20)]
        )
        rows.append(
            {
                "chunks": len(store._chunks),
                "ingest_ms": ingest_ms,
                "rebuild_s": rebuild,
                "search_ms": each,
            }
        )
    return rows


def corpus(targets) -> dict | None:
    import measure_outcomes as outcomes

    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    gate = SecurityGate(
        GatePolicy(), allowed_repositories=[name for name, _ in targets]
    )
    store = DocumentStore(gate)
    with contextlib.redirect_stdout(io.StringIO()):
        outcomes.ingest(targets, store, gate)
    retriever = BM25Retriever(store)
    start = time.time()
    retriever.search("北極星指標", top_k=5)
    rebuild = time.time() - start
    each = _timed_searches(
        retriever, [question.question for question in OUTCOME_QUESTIONS][:20]
    )
    return {
        "documents": len(store._documents),
        "chunks": len(store._chunks),
        "rebuild_s": rebuild,
        "search_ms": each,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    print("合成の梯子（形を見るためのもの。**率は実コーパスの方が高い**——"
          "短い文書と 2 語のクエリなので、こちらが楽観側）")
    print(f"{'chunks':>8} {'ingest/件(ms)':>14} {'再構築(s)':>11} {'検索(ms)':>10}")
    rows = ladder()
    for row in rows:
        print(
            f"{row['chunks']:>8} {row['ingest_ms']:>14.2f} "
            f"{row['rebuild_s']:>11.2f} {row['search_ms']:>10.1f}"
        )
    if arguments:
        import measure_outcomes as outcomes

        targets, missing = outcomes.parse_targets(arguments)
        if missing is None:
            return 2
        real = corpus(targets)
        print()
        print(
            f"実コーパス: {real['documents']} 文書 / {real['chunks']} 断片・"
            f"再構築 {real['rebuild_s']:.2f}s・検索 {real['search_ms']:.1f}ms"
        )
        rate = real["search_ms"] / max(1, real["chunks"])
        print(
            f"実測の 1 断片あたり {rate * 1000:.1f}µs。この率のままなら "
            f"検索が {SLOW_SEARCH_MS:.0f}ms に届くのは約 "
            f"{int(SLOW_SEARCH_MS / rate):,} 断片——**外挿であって実測ではない**"
        )
    print()
    print(
        "検索は全断片を走査する（適格性フィルタ）ので断片数に比例し、"
        "`add` のたびに索引が無効化されるので取り込みは断片数に比例した"
        "再構築を毎回払う。器を替える価値はこの 2 本の線の傾きにある。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
