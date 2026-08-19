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

Paraphrased questions currently score zero, so their floor is zero and guards
nothing. It is kept, and every run that measures zero says so on its own line
and again in the summary, because a floor deleted for being vacuous is a
question nobody asks again. Raise it as soon as a run scores higher.

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

#: Measured 2026-08-19 12:21 over all five repositories, against the corpus
#: the product actually ingests: 7/18 answerable, 7/11 direct, 0/7
#: paraphrased, discrimination +27.8 points.
#:
#: These floors replace ones pinned hours earlier to 8/18, 7/11 and 1/7. That
#: measurement walked every text file in each checkout - 426 documents the
#: ingestion pipeline never reads - so it described a system that does not
#: exist. The floors derived from it went red against a green main the moment
#: the corpus was corrected, which is the worse failure: a check that cries
#: wolf gets switched off, and then nothing is guarded at all.
#:
#: Each floor sits one question below what was measured, for churn in the four
#: repositories this project does not own.
MIN_ANSWERED = 6
MIN_DIRECT = 6

#: Zero, because that is what paraphrased questions actually score.
#:
#: The previous floor of 1 was argued for on the grounds that the paraphrase
#: rate must never be allowed to reach zero silently. The argument was right
#: and the number was wrong: it had already been zero. The single hit it was
#: pinned to came from a ``.tsx`` file the product does not ingest, so the
#: floor asserted a level the real system had never reached.
#:
#: A floor of zero guards nothing, and pretending otherwise is worse than
#: saying so - which is why a run that measures zero says so on every line of
#: output rather than passing quietly. This is a recorded failure, not a
#: target that has been met. The local-embedding work meant to move it was
#: approved on 2026-08-19 and is being built in parts; its skeleton is
#: deliberately identical to BM25, so this number cannot move until a real
#: backend is wired in. Raise it the moment a run scores higher: an
#: improvement nobody ratchets is an improvement that regresses unnoticed.
MIN_PARAPHRASE = 0

#: Discrimination, in points. Measured at +27.8. The floor is well below that
#: because the quantity is noisier than the others - it moves when any of five
#: repositories gains a document that looks like an answer to someone else's
#: question - and because its job is to catch a collapse, not a wobble.
MIN_DISCRIMINATION_POINTS = 15.0

#: The numbers this file enforces, under the names a backlog item may promise
#: to move.
#:
#: `product_metrics.py` is not the only place outcome numbers live. It has to
#: run offline in seconds, so it cannot measure anything that needs the four
#: external checkouts - which is exactly why the answerable numbers are
#: enforced here instead. A backlog item promising to move one of these is
#: promising something real, and
#: `tests/test_product_metrics.py::test_every_metric_the_backlog_names_exists`
#: reads both registries so it can tell that from a promise about a number
#: nobody measures.
#:
#: One name per floor above. `test_answerable_metric_names_track_the_floors`
#: fails if a floor is added without one, because a floor with no name cannot
#: be promised and a name with no floor guards nothing.
METRIC_KEYS = frozenset(
    {
        "answerable_total",
        "answerable_direct",
        "answerable_paraphrase",
        "answerable_discrimination",
    }
)


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
    paraphrase_note = ""
    if paraphrase["answered"] == 0:
        paraphrase_note = "  <- 既知のゼロ。守っていない（埋め込み実装中・C 節）"
    elif paraphrase["answered"] > MIN_PARAPHRASE:
        paraphrase_note = f"  <- 下限 {MIN_PARAPHRASE} を上回った。この下限を上げること"
    print(
        f"  paraphrase   : {paraphrase['answered']}/{paraphrase['scored']}  "
        f"(floor {MIN_PARAPHRASE}){paraphrase_note}"
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

    if paraphrase["answered"] == 0:
        # Passing on a floor of zero is not the same as being fine. Saying so
        # here is the whole reason a vacuous floor is allowed to exist rather
        # than being quietly deleted.
        print(
            "\nOK: every floor held - but paraphrase is 0/"
            f"{paraphrase['scored']} and its floor guards nothing. "
            "That is the recorded state, not a passing grade."
        )
        return 0

    print("\nOK: every floor held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
