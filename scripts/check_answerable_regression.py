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

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "src"))

from measure_outcomes import (  # noqa: E402
    head_sha,
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
#: Re-pinned 2026-08-19 after the question set grew from 18 to 26 (four
#: CreatorYard and two marketing direct questions, two CreatorYard
#: paraphrases): measured 11/26 answered, 10/15 direct, 1/11 paraphrased,
#: discrimination +30.8. One question of slack, as before.
#: Re-pinned 2026-08-20 for 27 questions (`para-ugc-safety-before-players`):
#: measured 11/27 answered, 10/15 direct, 1/12 paraphrased, discrimination
#: +25.9. The lexical numbers did not move - the added question is a
#: paraphrase, and BM25 answers exactly one of those - so these two stand.
#: Re-pinned 2026-08-23 for 38 questions (eight creator-facing questions from
#: C-984, three marketing paraphrases from C-982): measured 13/38 answered,
#: 11/18 direct, 2/20 paraphrased, discrimination +23.7. The old 10/9 carried
#: three and two questions of slack against that, which is looser than this
#: file's own policy and would have let the C-984 gains leak away unnoticed.
#: Back to one below the measurement.
MIN_ANSWERED = 12
MIN_DIRECT = 10

#: Floors for the semantic configuration (weights present and configured).
#: Measured 2026-08-19 with intfloat/multilingual-e5-small: 13/26 answered,
#: 11/15 direct, 2/11 paraphrased, discrimination unchanged at +30.8. One
#: below, same slack policy. Two sets because the two configurations are two
#: products: a machine without weights must keep passing at the lexical
#: floors, and a machine with weights must not be allowed to quietly perform
#: like a machine without them.
#: Re-pinned 2026-08-20 for 27 questions: measured 14/27 answered, 11/15
#: direct, 3/12 paraphrased, discrimination +33.3. `answered` moves 12 -> 13
#: because the set grew and the added question is answered here; this is a
#: re-pin to the new set, NOT an improvement (the judge refused to bank it,
#: which is correct - the denominator moved).
#: `paraphrase` stays at 2 on purpose, even though the run printed the
#: ratchet prompt at 3. That prompt exists because this floor used to be
#: pinned AT measurement, and the comment below says why: one-below would
#: have been zero, and zero guards nothing. At a measurement of 3 that
#: reason has expired, so the file's general policy applies again - one
#: question of slack for churn in the four repositories this project does
#: not own. The new question's evidence lives in someone else's sales copy,
#: which is exactly the churn the slack is for.
#: Re-pinned 2026-08-23 on the 38-question set, measured with the weights
#: fetched that day: 18/38 answered, 13/18 direct, 5/20 paraphrased,
#: discrimination +34.2. One below each, same slack policy. The paraphrase
#: floor moving 2 -> 4 is the point of C-982: the tier now covers all five
#: repositories, and a machine with weights answering five of them must not
#: be allowed to drop back to two while the headline holds.
SEMANTIC_MIN_ANSWERED = 17
SEMANTIC_MIN_DIRECT = 12
SEMANTIC_MIN_PARAPHRASE = 4

#: One, as of 2026-08-19: `para-cy-unfinished-work` retrieves
#: "完成度で人を落とさない" at rank 2 on the product-identical corpus. The
#: first paraphrase hit this project has had, and the reason this floor is
#: no longer zero. It is deliberately NOT one-below-measurement: one below
#: would be zero, zero guards nothing, and the entire point of this number
#: is that the paraphrase rate must never return to zero silently. If this
#: fails against a green main because the CreatorYard culture line moved,
#: lower it back with the reason in the commit - that is the documented
#: escape hatch, not a reason to leave the floor vacuous.
#: Still one on the 38-question set: BM25 measured 2/20 on 2026-08-23, and
#: one below a measurement of two is one. The three marketing paraphrases
#: added that day retrieve nothing lexically, which is the expected shape of
#: this tier and not a reason to move the floor.
MIN_PARAPHRASE = 1

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


#: What each number is allowed to prove under ``--compare``, mirroring
#: ``product_metrics.py``: an *outcome* moving up is completion evidence, a
#: *guard* moving down is a regression, and a guard moving up proves nothing.
#: ``answerable_mrr`` is a guard here for the same reason discrimination is:
#: both can be traded away silently while a headline count improves, so a
#: drop must fail the run, but a rise must not be bankable as "done".
_OUTCOME_KEYS = (
    "answerable_total",
    "answerable_direct",
    "answerable_paraphrase",
    "excerpt_hits_marker",
    "game_production_answered",
)
_GUARD_KEYS = ("answerable_discrimination", "answerable_mrr")

#: Smallest guard change that counts as movement rather than measurement
#: noise. The outcome keys are integer question counts and need no slack.
_GUARD_MIN_MOVE = {"answerable_discrimination": 2.0, "answerable_mrr": 0.02}


def _retriever_label() -> str:
    """Which ranking configuration produced this measurement.

    Snapshots must say what ranked them: a --save taken on plain BM25 and a
    --compare run with a semantic model measure two different products, and
    the movement between them belongs to the configuration change - which is
    sometimes exactly the change under test, but must never pass silently.
    """

    import os as _os

    return (
        "bm25+semantic"
        if _os.environ.get("SIDRA_EMBEDDING_MODEL_PATH", "").strip()
        else "bm25"
    )


def _snapshot(result: dict, targets: list[tuple[str, "Path"]]) -> dict:
    direct = result["by_tier"].get("direct", {"answered": 0})
    paraphrase = result["by_tier"].get("paraphrase", {"answered": 0})
    excerpt = result.get("excerpt") or {"shows_marker": 0, "answered": 0}
    game = result.get("game_production") or {"answered": 0, "scored": 0}
    return {
        "answerable_total": result["answered"],
        "answerable_direct": direct["answered"],
        "answerable_paraphrase": paraphrase["answered"],
        "answerable_discrimination": round(100 * result["discrimination"], 1),
        "answerable_mrr": round(result["mrr"], 3),
        # Of the questions whose evidence came back, how many show the answer
        # inside the excerpt the citation carries. Its denominator is
        # `answered`, which moves on its own, so it is recorded beside the
        # count and `_compare` refuses to bank a rise across a change of it.
        "excerpt_hits_marker": excerpt["shows_marker"],
        "excerpt_scored": excerpt["answered"],
        # The creator-facing subset, recorded beside its own denominator for
        # the same reason: these counts are only comparable over the same
        # questions, and the set grows as coverage is filled in.
        "game_production_answered": game["answered"],
        "game_production_scored": game["scored"],
        # The corpus is other people's repositories and it moves on its own.
        # Recording the heads makes "the number moved" attributable: if the
        # heads differ between --save and --compare, the movement may belong
        # to someone else's push, not to the change under test.
        "corpus_heads": {repo: head_sha(path)[:12] for repo, path in targets},
        # Question-set sizes. Counts are only comparable over the same set:
        # adding an easy question raises `answered` without the product
        # changing, which would make writing questions bankable as progress.
        "retriever": _retriever_label(),
        "scored": {
            "direct": direct.get("scored", 0),
            "paraphrase": paraphrase.get("scored", 0),
        },
    }


def _compare(before: dict, now: dict) -> int:
    """Report movement since ``before`` with product_metrics semantics.

    Exit 0: an outcome count rose. Exit 1: nothing moved. Exit 2: an outcome
    fell or a guard dropped by more than its noise floor. Floor enforcement
    has already happened by the time this runs, so a run that gets here is at
    least as good as the pinned floors.
    """

    if before.get("retriever") not in (None, now.get("retriever")):
        print(
            f"retriever changed between --save and --compare: "
            f"{before.get('retriever')} -> {now.get('retriever')}. Movement "
            "below is attributable to that configuration change."
        )

    drifted = [
        f"{repo} {before.get('corpus_heads', {}).get(repo, '?')} -> {sha}"
        for repo, sha in now.get("corpus_heads", {}).items()
        if before.get("corpus_heads", {}).get(repo) not in (None, sha)
    ]
    if drifted:
        print(
            "corpus moved between --save and --compare: " + "; ".join(drifted)
        )
        print(
            "Movement below may belong to those pushes rather than to the "
            "change under test. Re-run --save on the current corpus if in doubt."
        )

    same_set = before.get("scored") == now.get("scored")
    if not same_set and before.get("scored") is not None:
        print(
            "question set changed between --save and --compare "
            f"({before.get('scored')} -> {now.get('scored')}): counts are not "
            "comparable, so outcome increases are NOT banked this run. "
            "Re-run --save on the new set; only a same-set improvement counts. "
            "Rate guards (discrimination/MRR) are judged by absolute floor "
            "only this run, for the same reason."
        )

    # The excerpt count is scored over `answered` questions, and that
    # denominator is not ours: four of the five repositories move on their own.
    # Comparing 6/10 against 6/9 as if both were "6" would let a retrieval
    # regression read as an excerpt improvement, so a changed denominator
    # makes the count incomparable in both directions rather than merely
    # unbankable.
    same_excerpt_set = before.get("excerpt_scored") in (
        None, now.get("excerpt_scored")
    )
    same_game_set = before.get("game_production_scored") in (
        None, now.get("game_production_scored")
    )
    if not same_game_set:
        print(
            "game-production question set changed between --save and --compare "
            f"({before.get('game_production_scored')} -> "
            f"{now.get('game_production_scored')} scored): "
            "game_production_answered is not comparable this run."
        )
    if not same_excerpt_set:
        print(
            "excerpt denominator changed between --save and --compare "
            f"({before.get('excerpt_scored')} -> {now.get('excerpt_scored')} "
            "answered): excerpt_hits_marker is not comparable this run."
        )

    moved: list[str] = []
    broken: list[str] = []
    for key in _OUTCOME_KEYS:
        old, new_value = before.get(key), now[key]
        if key == "excerpt_hits_marker" and old is not None and not same_excerpt_set:
            continue
        if key == "game_production_answered" and old is not None and not same_game_set:
            continue
        if old is None:
            moved.append(f"{key} (newly measured) -> {new_value}")
        elif new_value > old:
            if same_set or before.get("scored") is None:
                moved.append(f"{key} {old} -> {new_value}")
        elif new_value < old:
            broken.append(f"{key} {old} -> {new_value}")
    for key in _GUARD_KEYS:
        old, new_value = before.get(key), now[key]
        if old is None:
            continue
        if not same_set and before.get("scored") is not None:
            # 2026-08-23 (CEO direction, option a): discrimination and MRR
            # are rates over the scored set, so adding harder questions
            # lowers them mechanically. Across a set change the *relative*
            # guard is not comparable in either direction - the absolute
            # floors (MIN_DISCRIMINATION_POINTS and friends) have already
            # gated this run before _compare was reached, and they alone
            # decide. Without this, adding a question was always judged a
            # regression, and the set could never honestly grow.
            continue
        if old - new_value >= _GUARD_MIN_MOVE[key]:
            broken.append(f"{key} {old} -> {new_value} (guard)")

    for line in broken:
        print(f"  WORSE  {line}")
    for line in moved:
        print(f"  BETTER {line}")
    print()
    if broken:
        print(f"REGRESSED: {len(broken)} number(s) moved the wrong way. Do not merge.")
        return 2
    if not moved:
        print("NO MOVEMENT: no answerable outcome changed.")
        return 1
    print(f"MOVED: {len(moved)} outcome number(s).")
    for line in moved:
        print(f"LOOP_LOG: {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 2

    save_path: Path | None = None
    compare_path: Path | None = None
    for flag in ("--save", "--compare"):
        if flag in arguments:
            index = arguments.index(flag)
            try:
                value = arguments[index + 1]
            except IndexError:
                print(f"{flag} needs a path", file=sys.stderr)
                return 2
            del arguments[index : index + 2]
            if flag == "--save":
                save_path = Path(value)
            else:
                compare_path = Path(value)
    if save_path and compare_path:
        print("--save and --compare are exclusive", file=sys.stderr)
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
    import os as _os
    from types import SimpleNamespace

    from sidra_ai.retrieval.embedding import build_retriever

    retriever = build_retriever(
        SimpleNamespace(
            embedding_model_path=_os.environ.get("SIDRA_EMBEDDING_MODEL_PATH", "").strip(),
            embedding_query_prefix=_os.environ.get("SIDRA_EMBEDDING_QUERY_PREFIX", ""),
            embedding_passage_prefix=_os.environ.get("SIDRA_EMBEDDING_PASSAGE_PREFIX", ""),
        ),
        store,
    )
    backend = getattr(retriever, "backend_name", "bm25")
    semantic = bool(getattr(retriever, "semantic_enabled", lambda: False)())
    print(f"retriever      : {'bm25 + ' + backend if semantic else 'bm25'}")
    result = measure_answerable(retriever, targets)

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

    semantic_run = _retriever_label() == "bm25+semantic"
    min_answered = SEMANTIC_MIN_ANSWERED if semantic_run else MIN_ANSWERED
    min_direct = SEMANTIC_MIN_DIRECT if semantic_run else MIN_DIRECT
    min_paraphrase = SEMANTIC_MIN_PARAPHRASE if semantic_run else MIN_PARAPHRASE
    print(f"answered       : {result['answered']}/{result['scored']}  (floor {min_answered})")
    print(f"  direct       : {direct['answered']}/{direct['scored']}  (floor {min_direct})")
    paraphrase_note = ""
    if paraphrase["answered"] == 0:
        paraphrase_note = "  <- 既知のゼロ。守っていない（埋め込み実装中・C 節）"
    elif paraphrase["answered"] > min_paraphrase:
        paraphrase_note = f"  <- 下限 {min_paraphrase} を上回った。この下限を上げること"
    print(
        f"  paraphrase   : {paraphrase['answered']}/{paraphrase['scored']}  "
        f"(floor {min_paraphrase}){paraphrase_note}"
    )
    print(
        f"discrimination : {discrimination:+.1f} pt  "
        f"(floor {MIN_DISCRIMINATION_POINTS:+.1f})"
    )
    print(f"MRR            : {result['mrr']:.3f}")
    game = result.get("game_production") or {}
    if game.get("scored"):
        print(
            f"game production : {game['answered']}/{game['scored']}"
            f"  ({100 * game['rate']:.1f}% of the creator-facing subset; "
            "no floor yet)"
        )
    excerpt = result.get("excerpt") or {}
    if excerpt.get("answered"):
        # No floor: this number was first measured 2026-08-22 and a floor
        # pinned on one reading is a floor pinned on noise. It is reported and
        # compared; pin it once there are two runs to compare.
        print(
            f"excerpt hit    : {excerpt['shows_marker']}/{excerpt['answered']}"
            f"  ({100 * excerpt['rate']:.1f}% of answered; no floor yet)"
        )

    failures: list[str] = []
    if result["answered"] < min_answered:
        failures.append(f"answered {result['answered']} < {min_answered}")
    if direct["answered"] < min_direct:
        failures.append(f"direct {direct['answered']} < {min_direct}")
    if paraphrase["answered"] < min_paraphrase:
        failures.append(f"paraphrase {paraphrase['answered']} < {min_paraphrase}")
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
        # Under --compare a floor failure is a regression, not a mere miss.
        return 2 if compare_path else 1

    if paraphrase["answered"] == 0:
        # Passing on a floor of zero is not the same as being fine. Saying so
        # here is the whole reason a vacuous floor is allowed to exist rather
        # than being quietly deleted.
        print(
            "\nOK: every floor held - but paraphrase is 0/"
            f"{paraphrase['scored']} and its floor guards nothing. "
            "That is the recorded state, not a passing grade."
        )
    else:
        print("\nOK: every floor held.")

    snapshot = _snapshot(result, targets)
    if save_path is not None:
        save_path.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"saved -> {save_path}")
    if compare_path is not None:
        print()
        return _compare(
            json.loads(compare_path.read_text(encoding="utf-8")), snapshot
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
