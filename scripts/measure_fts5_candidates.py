"""How many candidates does FTS5 have to offer before ranking stops changing? (C-1466)

C-1464 measured the whole swap and rejected it: FTS5's ``bm25()`` is fixed at
k1=1.2 where this corpus is tuned to k1=1.5, and the judge lost an answer
(``answered`` 14->13, MRR 0.284->0.272). It also measured what FTS5 is good
at - search 68x faster - and pointed at the split that keeps both: let FTS5
say *which* chunks to score, keep this project's BM25 to say *how well*.

That split is only worth anything if the shortlist contains the chunks that
would have won anyway, and how big it has to be for that is not derivable -
FTS5 orders candidates by a different BM25 than the one doing the ranking. So
this sweeps the pool size and measures two things at each step:

* **identity** - the fraction of judge questions whose top-5 is exactly what
  a full scan returns, same chunks in the same order. This is the honest
  measure of "did narrowing change the answer", and it is stricter than the
  judge: a pool can score 100% on the judge while quietly reordering results
  the judge does not ask about.
* the judge's own four numbers, so a pool that trades one for the other is
  visible rather than averaged away.

    python scripts/measure_fts5_candidates.py <repo=path ...>

Exit 0 always: a measurement, not a gate.
"""

import contextlib
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import measure_outcomes as mo  # noqa: E402
from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS  # noqa: E402
from sidra_ai.retrieval.candidates import Fts5CandidateSource, fts5_available  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

#: Pool sizes, as a multiple of the requested ``top_k``. The low end is there
#: to be wrong: if 5x already reproduced the full scan there would be no curve
#: to record, and a sweep that only contains safe values proves nothing.
MULTIPLIERS = (2, 5, 10, 20, 40, 80, 160)

TOP_K = 5


def _timed_search(retriever, questions, *, top_k=TOP_K):
    """Return (results per question, mean milliseconds per search)."""

    start = time.perf_counter()
    results = [retriever.search(q, top_k=top_k) for q in questions]
    elapsed = 1000 * (time.perf_counter() - start) / max(len(questions), 1)
    return results, elapsed


def _timed_search_filtered(retriever, questions, repositories, *, top_k=TOP_K):
    start = time.perf_counter()
    results = [
        retriever.search(q, top_k=top_k, repositories=repositories) for q in questions
    ]
    elapsed = 1000 * (time.perf_counter() - start) / max(len(questions), 1)
    return results, elapsed


def _fingerprint(results):
    return tuple(r.chunk.chunk_id for r in results)


def main(argv):
    targets, missing = mo.parse_targets(argv)
    if missing is None or not targets:
        print(__doc__, file=sys.stderr)
        return 2
    if not fts5_available():
        print("この Python の SQLite に FTS5 が無い。候補生成は使えない。")
        return 0

    gate = SecurityGate(GatePolicy(), allowed_repositories=[n for n, _ in targets])
    store = DocumentStore(gate)
    with contextlib.redirect_stdout(io.StringIO()):
        mo.ingest(targets, store, gate)

    questions = [q.question for q in OUTCOME_QUESTIONS]
    total_chunks = len(tuple(store.chunks()))
    print(f"実コーパス: {total_chunks} 断片 / 判定器 {len(questions)} 問 / top_k={TOP_K}")
    print()

    # The reference: a full scan, no candidate source.
    plain = BM25Retriever(store)
    build_start = time.perf_counter()
    plain.search("暖機", top_k=TOP_K)
    plain_build = time.perf_counter() - build_start
    base_results, base_ms = _timed_search(plain, questions)
    base_fingerprints = [_fingerprint(r) for r in base_results]
    with contextlib.redirect_stdout(io.StringIO()):
        base_out = mo.measure_answerable(plain, targets)
    scored = base_out["scored"] or 1

    # Two changes ship together in C-1466 and they must not be reported as
    # one number. Passing every repository as an explicit filter reproduces
    # the per-query statistics rebuild that the unfiltered path used to do
    # unconditionally, over the identical chunk set - so this row is what
    # search cost before either change, measured rather than remembered.
    every_repository = [name for name, _ in targets]
    _, rebuild_ms = _timed_search_filtered(plain, questions, every_repository)

    def tier(out, name):
        bucket = out["by_tier"].get(name) or {"answered": 0, "scored": 0}
        return f"{bucket['answered']}/{bucket['scored']}"

    def line(label, out, identity, ms, pool):
        disc = 100 * out["discrimination"]
        print(
            f"{label:>12s} {str(pool):>6} {out['answered']:>5}/{scored}"
            f" {tier(out, 'direct'):>7} {tier(out, 'paraphrase'):>7}"
            f"  {out.get('mrr', 0):.3f}  {disc:+6.1f}pt"
            f"  {identity:>6}  {ms:7.2f}ms"
        )

    header = (
        f"{'':>12s} {'候補':>6} {'answered':>8} {'direct':>7} "
        f"{'言換':>7}  {'MRR':>5}  {'弁別':>7}  {'同一':>6}  {'検索':>9}"
    )
    print(header)
    print("-" * len(header))
    print(
        f"{'統計を毎回':>12s} {'-':>6} {'':>5} {'':>7} {'':>7}"
        f"  {'':>5}  {'':>7}  {'':>6}  {rebuild_ms:7.2f}ms   <- 変更前の全走査"
    )
    line("BM25(全走査)", base_out, f"{len(questions)}/{len(questions)}", base_ms, "-")

    source_start = time.perf_counter()
    source = Fts5CandidateSource.from_chunks(store.chunks())
    source_build = time.perf_counter() - source_start
    rows = []
    for multiplier in MULTIPLIERS:
        pool = TOP_K * multiplier
        hybrid = BM25Retriever(store, candidate_source=source, candidate_pool=pool)
        hybrid.search("暖機", top_k=TOP_K)
        results, ms = _timed_search(hybrid, questions)
        same = sum(
            1
            for got, want in zip(results, base_fingerprints)
            if _fingerprint(got) == want
        )
        with contextlib.redirect_stdout(io.StringIO()):
            out = mo.measure_answerable(hybrid, targets)
        line(f"+FTS5 x{multiplier}", out, f"{same}/{len(questions)}", ms, pool)
        rows.append((multiplier, pool, same, out, ms))

    print()
    perfect = [r for r in rows if r[2] == len(questions)]
    if perfect:
        smallest = min(perfect, key=lambda r: r[0])
        speedup = base_ms / smallest[4] if smallest[4] else float("inf")
        print(
            f"全 {len(questions)} 問で全走査と同一の順位になる最小の候補数: "
            f"{smallest[1]}（top_k x{smallest[0]}）・検索 {base_ms:.2f}ms -> "
            f"{smallest[4]:.2f}ms（{speedup:.1f} 倍）"
        )
    else:
        print(
            "どの候補数でも全走査と同じ順位にならなかった。"
            "候補生成は採用しない（順位が変わるなら係数を守った意味が無い）。"
        )
    shared = BM25Retriever(store, candidate_source=Fts5CandidateSource())
    shared_start = time.perf_counter()
    shared.search("暖機", top_k=TOP_K)
    shared_build = time.perf_counter() - shared_start
    print(
        f"索引: BM25 単体 {plain_build:.2f}s ／ FTS5 候補索引を別に建てると"
        f" ＋{source_build:.2f}s ／ 製品の経路（トークンを渡して共用）"
        f" {shared_build:.2f}s"
    )
    print(
        "注: 同一 = 上位 5 件が全走査と同じ断片・同じ順。判定器の 4 数字より厳しい。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
