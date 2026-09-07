"""How many chunks should reach the model? Measured, not guessed (C-1134).

The context budget admits far more than the five chunks retrieval hands
over, so the obvious question is whether the spare room is worth anything.
This answers it by walking the retrieval depth and printing, at each one,
the two numbers that have to be read together:

* **answered** - the question's own evidence came back, and
* **control** - some *other* repository's answer marker came back too.

Five repositories that all discuss the same business will surface plausible
neighbours for almost any query, so a rising answer rate means nothing on
its own. ``measure_outcomes`` already computes both and the regression judge
already floors their difference (discrimination); this walks that pair
across depths so the choice of five can be defended with a curve instead of
a preference.

    python scripts/measure_context_depth.py \\
        tukemen-rgb/sidra-ai=. \\
        tukemen-rgb/site=/home/user/site \\
        tukemen-rgb/creater-yard=/home/user/tukemen-rgb/creater-yard \\
        tukemen-rgb/Fg=/home/user/tukemen-rgb/Fg \\
        tukemen-rgb/marketing=/home/user/marketing

Same five checkouts the regression judge needs, and for the same reason: a
rate measured over part of the corpus is not comparable with anything.

Exit 0 always. This is a measurement, not a gate - the gate is
``check_answerable_regression.py``, whose discrimination floor is what
actually stops a depth that buys answers with noise.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import measure_outcomes as outcomes  # noqa: E402

from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

#: The depths worth printing: below the shipped five, at it, and out to the
#: point where the neighbours win.
DEPTHS: tuple[int, ...] = (3, 5, 6, 8, 10, 15, 20)

#: The floor the regression judge holds discrimination to. Printed beside
#: each row so a depth that would break it is visible here rather than only
#: in the judge that refuses it.
DISCRIMINATION_FLOOR = 15.0


def sweep(retriever, targets) -> list[dict]:
    """The judge's own measurement, run once per depth.

    ``measure_answerable`` is called rather than reimplemented: a second
    definition of "answered" is a second product, and the one that would
    drift is the one nobody runs.
    """

    rows = []
    original = outcomes.TOP_K
    try:
        for depth in DEPTHS:
            outcomes.TOP_K = depth
            with contextlib.redirect_stdout(io.StringIO()):
                result = outcomes.measure_answerable(retriever, targets)
            scored = result["scored"] or 1
            answered_rate = 100 * result["answered"] / scored
            control_rate = 100 * result["control_hits"] / scored
            rows.append(
                {
                    "depth": depth,
                    "answered": result["answered"],
                    "scored": result["scored"],
                    "control": result["control_hits"],
                    "mrr": result.get("mrr", 0.0),
                    "discrimination": answered_rate - control_rate,
                }
            )
    finally:
        outcomes.TOP_K = original
    return rows


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 2
    targets, missing = outcomes.parse_targets(arguments)
    if missing is None:
        return 2
    required = {question.repository for question in OUTCOME_QUESTIONS}
    absent = sorted(required - {name for name, _ in targets}) + sorted(missing)
    if absent:
        print("refusing to measure: not checked out: " + ", ".join(absent), file=sys.stderr)
        return 2

    gate = SecurityGate(GatePolicy(), allowed_repositories=[name for name, _ in targets])
    store = DocumentStore(gate)
    with contextlib.redirect_stdout(io.StringIO()):
        outcomes.ingest(targets, store, gate)
    rows = sweep(BM25Retriever(store), targets)

    print(f"{'深さ':>4} {'answered':>9} {'control':>8} {'差(pt)':>8} {'MRR':>7}")
    for row in rows:
        mark = "" if row["discrimination"] >= DISCRIMINATION_FLOOR else "  <- 下限割れ"
        print(
            f"{row['depth']:>4} {row['answered']:>4}/{row['scored']:<4} "
            f"{row['control']:>8} {row['discrimination']:>8.1f} {row['mrr']:>7.3f}{mark}"
        )
    print()
    print(
        "answered だけを読むと深いほど良く見える。control は「別リポジトリの"
        "答え」が同じ結果集合に現れた回数で、深さと一緒に増える——差が"
        f"{DISCRIMINATION_FLOOR:.0f} pt を割ったところから先は、答えを"
        "近所ごとすくっているだけ。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
