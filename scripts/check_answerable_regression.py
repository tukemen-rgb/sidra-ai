"""Fail when SIDRA gets worse at answering the questions it is asked.

The false-positive rate was measured for weeks and nothing enforced it; a
change that doubled it would have passed. ``check_gate_regression.py`` turned
that measurement into a control. The answerable rate is in the state the flag
rate used to be in: measured once, written into ``docs/OUTCOMES.md``, and
protected by nothing at all. This is its counterpart.

    python scripts/check_answerable_regression.py \\
        tukemen-rgb/sidra-ai=. \\
        tukemen-rgb/site=/workspace/tukemen-rgb/site \\
        tukemen-rgb/creater-yard=/workspace/tukemen-rgb/creater-yard \\
        tukemen-rgb/Fg=/workspace/tukemen-rgb/Fg \\
        tukemen-rgb/marketing=/workspace/tukemen-rgb/marketing

Run it before and after anything that touches retrieval, chunking, the
tokenizer, or the security gate. The gate belongs in that list: it decides
what is in the index at all, so tightening a detector can remove the document
that answered a question. That trade has been invisible until now - the
safety number moved in its own report and the product number moved in
nobody's.

Four floors, not one
--------------------

A single blended rate is exactly the shape of number this project has already
been burned by. Direct-word and paraphrased questions fail for unrelated
reasons - ranking versus vocabulary - so a gain on one can hide a collapse in
the other while the headline holds steady. They are floored separately.

The fourth floor is on discrimination: answerable minus the share of
questions whose result set contains evidence belonging to some *other*
repository. All five repositories discuss the same business, so a retriever
that returned plausible neighbours for everything would post a fine
answerable rate while being useless. If discrimination collapses, the other
three numbers stop meaning anything, and a floor that can be satisfied by
becoming less discriminating is not a floor.

Why counts rather than rates
----------------------------

Eighteen questions make one question worth 5.6 points, so a rate floor is a
count floor wearing a disguise; the count says plainly what it takes to fail.
Unlike the flag rate, this number does not drift when someone adds files -
adding a clean document cannot make a question answerable - so the floors do
not need slack for ordinary commits.

They do need slack for one thing: four of the five repositories are cloned at
their own HEAD and belong to other people. Somebody editing ``site`` can
change what answers a question here. The floors therefore sit one question
below the measurement rather than exactly on it. Two questions of movement is
the corpus telling you something; one can be someone else's Tuesday.

Lowering a floor is allowed. It takes a deliberate edit to this file and a
reason in the commit message - the same mechanism, and the same intent, as
``MAX_FLAG_RATE``.

No document content is printed: question names, counts and ranks only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "src"))

from measure_outcomes import (  # noqa: E402
    ingest,
    measure_answerable,
    parse_targets,
)
from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

#: Measured 2026-08-19 over all five repositories: 8/18 answerable, 7/11
#: direct, 1/7 paraphrased, discrimination +27.8 points.
#:
#: Each floor sits one question below what was measured, for churn in the four
#: repositories this project does not own.
MIN_ANSWERED = 7
MIN_DIRECT = 6

#: One, and it cannot go lower. The paraphrase rate is already at the bottom
#: of its range - a single question - so there is no room to absorb churn, and
#: none is wanted: this is the number the local-embedding decision in the
#: backlog's judgement section exists to raise. If it reaches zero, the thing
#: being decided about has silently stopped working.
MIN_PARAPHRASE = 1

#: Discrimination, in points. Measured at +27.8. The floor is well below that
#: because the quantity is noisier than the others - it moves when any of five
#: repositories gains a document that looks like an answer to someone else's
#: question - and because its job is to catch a collapse, not a wobble.
MIN_DISCRIMINATION_POINTS = 15.0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 2

    targets, missing = parse_targets(arguments)
    if missing is None:
        return 2

    # A partial checkout must not produce a number. Four repositories out of
    # five would score lower for a reason that has nothing to do with the
    # change under test, and a floor that fails for the wrong reason gets
    # lowered by whoever is unlucky enough to hit it.
    required = {question.repository for question in OUTCOME_QUESTIONS}
    present = {repository for repository, _path in targets}
    absent = sorted(required - present) + sorted(missing)
    if absent:
        print(
            "refusing to measure: these repositories are not checked out: "
            + ", ".join(absent),
            file=sys.stderr,
        )
        print(
            "A rate measured over part of the corpus is not comparable with "
            "the floors in this file.",
            file=sys.stderr,
        )
        return 2

    gate = SecurityGate(
        GatePolicy(), allowed_repositories=[repository for repository, _ in targets]
    )
    store = DocumentStore(gate)
    ingest(targets, store, gate)
    result = measure_answerable(BM25Retriever(store), targets)

    if result["ungrounded"]:
        print(
            "refusing to measure: no evidence in the corpus for "
            + ", ".join(result["ungrounded"]),
            file=sys.stderr,
        )
        return 2

    direct = result["by_tier"].get("direct", {"answered": 0, "scored": 0})
    paraphrase = result["by_tier"].get("paraphrase", {"answered": 0, "scored": 0})
    discrimination = 100 * result["discrimination"]

    print(f"answered       : {result['answered']}/{result['scored']}  (floor {MIN_ANSWERED})")
    print(f"  direct       : {direct['answered']}/{direct['scored']}  (floor {MIN_DIRECT})")
    print(
        f"  paraphrase   : {paraphrase['answered']}/{paraphrase['scored']}  "
        f"(floor {MIN_PARAPHRASE})"
    )
    print(
        f"discrimination : {discrimination:+.1f} pt  "
        f"(floor {MIN_DISCRIMINATION_POINTS:+.1f})"
    )
    print(f"MRR            : {result['mrr']:.3f}")

    failures: list[str] = []
    if result["answered"] < MIN_ANSWERED:
        failures.append(f"answered {result['answered']} < {MIN_ANSWERED}")
    if direct["answered"] < MIN_DIRECT:
        failures.append(f"direct {direct['answered']} < {MIN_DIRECT}")
    if paraphrase["answered"] < MIN_PARAPHRASE:
        failures.append(f"paraphrase {paraphrase['answered']} < {MIN_PARAPHRASE}")
    if discrimination < MIN_DISCRIMINATION_POINTS:
        failures.append(
            f"discrimination {discrimination:+.1f} < {MIN_DISCRIMINATION_POINTS:+.1f}"
        )

    if failures:
        print(f"\nFAILED: {'; '.join(failures)}", file=sys.stderr)
        print(
            "SIDRA answers fewer of the real questions than it did. Run "
            "`measure_outcomes.py --diagnose` to see which ones and how far "
            "the evidence was, before deciding whether this is a regression "
            "or a floor worth lowering.",
            file=sys.stderr,
        )
        missed = [row["name"] for row in result["rows"] if row["status"] == "miss"]
        if missed:
            print("\nmissed: " + ", ".join(missed), file=sys.stderr)
        return 1

    print("\nOK: every floor held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
