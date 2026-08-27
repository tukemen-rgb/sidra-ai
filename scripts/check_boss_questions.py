"""Score the owner's twenty questions against the real five-repository index.

    python scripts/check_boss_questions.py \\
        tukemen-rgb/sidra-ai=. \\
        tukemen-rgb/site=<path> tukemen-rgb/creater-yard=<path> \\
        tukemen-rgb/Fg=<path> tukemen-rgb/marketing=<path> \\
        [--save before.json | --compare before.json]

Why this is a separate judge and not another line on
``check_answerable_regression.py``: that instrument has floors, and floors are
promises. This set has no history yet - its first run *is* its baseline - so
giving it floors today would either invent a promise nobody measured or set one
so low it guards nothing. It reports and compares; floors go in when there is a
series to floor.

Two numbers, and they answer different questions:

``boss_q_answered``
    The answer's own text came back in the top five, from the repository the
    question is about. This is the number C-1008 wanted.

``boss_q_wrong_repository``
    Nothing from the right repository came back, but *some other* repository's
    answer did. This is the failure C-1009 named: not silence, but a confident
    answer to a question nobody asked, which is worse than silence because it
    reads as reassurance. It is counted separately because a change can improve
    the first while making the second worse, and a blended figure would hide
    exactly that trade.

The exit code is the verdict, same contract as the other judges:
0 moved, 1 no movement, 2 regressed, 3 cannot judge.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "src"))

from measure_outcomes import ingest, parse_targets  # noqa: E402
from sidra_ai.evals.boss_questions import (  # noqa: E402
    BOSS_QUESTIONS,
    REPOSITORIES,
    grounded,
    headline,
)
from sidra_ai.retrieval.embedding import build_retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

EXIT_MOVED = 0
EXIT_NO_MOVEMENT = 1
EXIT_REGRESSED = 2
EXIT_CANNOT_JUDGE = 3

TOP_K = 5

#: Directions, so ``--compare`` cannot be read as "any change is progress".
DIRECTION = {
    "boss_q_answered": "up",
    "boss_q_wrong_repository": "down",
    "boss_q_scoreable": "up",
}


def measure(retriever, *, top_k: int = TOP_K) -> dict:
    """Ask every grounded question and record which of the two things happened."""

    answered = 0
    wrong_repository = 0
    rows = []
    missing_evidence = []

    others = {
        question.name: [
            other.answer_marker
            for other in headline()
            if other.repository != question.repository
        ]
        for question in headline()
    }

    for question in grounded():
        results = retriever.search(question.question, top_k=top_k)
        right = any(
            result.chunk.provenance.repository == question.repository
            and question.answer_marker in result.chunk.content
            for result in results
        )
        text = " ".join(result.chunk.content for result in results)
        foreign = any(marker in text for marker in others.get(question.name, ()))

        # Evidence that is nowhere in the index at all is a corpus problem, not
        # a retrieval score. Reported separately so a missing document cannot
        # be banked as "retrieval got worse".
        indexed = any(
            chunk.provenance.repository == question.repository
            and question.answer_marker in chunk.content
            for chunk in retriever.store.chunks()
        )
        if not indexed:
            missing_evidence.append(question.name)

        if question.self_grounded:
            rows.append((question, right, False))
            continue

        if right:
            answered += 1
        elif foreign:
            wrong_repository += 1
        rows.append((question, right, foreign and not right))

    return {
        "boss_q_answered": answered,
        "boss_q_wrong_repository": wrong_repository,
        "boss_q_scoreable": len(headline()),
        "denominator": len(headline()),
        "rows": rows,
        "missing_evidence": missing_evidence,
    }


def _compare(before: dict, now: dict) -> tuple[int, list[str]]:
    lines = []
    verdict = EXIT_NO_MOVEMENT

    # Two retrievers are two products. Comparing a semantic run against a
    # lexical baseline would read as a change to the code under test.
    if before.get("retriever", now.get("retriever")) != now.get("retriever"):
        lines.append(
            "retriever changed ({} -> {}): these are two configurations, not "
            "two versions.".format(before.get("retriever"), now["retriever"])
        )
        return EXIT_CANNOT_JUDGE, lines

    if before.get("denominator") != now["denominator"]:
        lines.append(
            "question set changed ({} -> {} scoreable): the counts below are "
            "not comparable.".format(before.get("denominator"), now["denominator"])
        )
        return EXIT_CANNOT_JUDGE, lines

    for key, direction in DIRECTION.items():
        if key not in before or key not in now:
            continue
        old, new = before[key], now[key]
        if new == old:
            continue
        better = new > old if direction == "up" else new < old
        lines.append(
            f"  {'BETTER' if better else 'WORSE '} {key} {old} -> {new}"
        )
        if better:
            if verdict != EXIT_REGRESSED:
                verdict = EXIT_MOVED
        else:
            verdict = EXIT_REGRESSED
    return verdict, lines


def _report(result: dict) -> None:
    total = result["denominator"]
    print(f"answered       : {result['boss_q_answered']}/{total}")
    print(f"wrong repository: {result['boss_q_wrong_repository']}/{total}")
    unanswerable = [q.name for q in BOSS_QUESTIONS if q.answer_marker is None]
    if unanswerable:
        print(
            "no answer in the corpus: "
            + ", ".join(unanswerable)
            + "  (kept in the set, out of the denominator)"
        )
    self_grounded = [q.name for q in grounded() if q.self_grounded]
    if self_grounded:
        print("scored but not in the headline (sidra-ai's own documents): "
              + ", ".join(self_grounded))
    print()
    print("These are not the 2026-08-26 figures. Different questions, so a 7")
    print("here is not that 7 - the series starts at this run.")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    save_path: Path | None = None
    compare_path: Path | None = None
    for flag in ("--save", "--compare"):
        if flag in arguments:
            index = arguments.index(flag)
            try:
                value = arguments[index + 1]
            except IndexError:
                print(f"{flag} needs a path", file=sys.stderr)
                return EXIT_REGRESSED
            del arguments[index : index + 2]
            if flag == "--save":
                save_path = Path(value)
            else:
                compare_path = Path(value)
    if save_path and compare_path:
        print("--save and --compare are exclusive", file=sys.stderr)
        return EXIT_REGRESSED

    targets, missing = parse_targets(arguments)
    if missing is None:
        return EXIT_REGRESSED

    present = {repository for repository, _path in targets}
    absent = sorted(set(REPOSITORIES) - present) + sorted(missing)
    if absent:
        print(
            "refusing to measure: these repositories are not checked out: "
            + ", ".join(absent),
            file=sys.stderr,
        )
        return EXIT_CANNOT_JUDGE

    gate = SecurityGate(
        GatePolicy(), allowed_repositories=[repository for repository, _ in targets]
    )
    store = DocumentStore(gate)
    ingest(targets, store, gate)

    # The same construction the product uses. Pinning BM25 here would make
    # this judge quietly measure a configuration nobody runs the moment a
    # local embedding model is configured - and the saved baseline would not
    # say which one it came from.
    retriever = build_retriever(
        SimpleNamespace(
            embedding_model_path=os.environ.get(
                "SIDRA_EMBEDDING_MODEL_PATH", ""
            ).strip(),
            embedding_query_prefix=os.environ.get("SIDRA_EMBEDDING_QUERY_PREFIX", ""),
            embedding_passage_prefix=os.environ.get(
                "SIDRA_EMBEDDING_PASSAGE_PREFIX", ""
            ),
        ),
        store,
    )
    semantic = bool(getattr(retriever, "semantic_enabled", lambda: False)())
    backend = (
        "bm25 + " + getattr(retriever, "backend_name", "?") if semantic else "bm25"
    )
    print(f"retriever      : {backend}")
    result = measure(retriever)
    result["retriever"] = backend

    if result["missing_evidence"]:
        print(
            "refusing to measure: the answering text is not in the index for "
            + ", ".join(result["missing_evidence"]),
            file=sys.stderr,
        )
        print(
            "Either the document moved or the gate is refusing it. A retrieval "
            "score measured over a corpus missing its own answers is not one.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_JUDGE

    _report(result)

    payload = {key: result[key] for key in DIRECTION}
    payload["denominator"] = result["denominator"]
    payload["retriever"] = result["retriever"]

    if save_path:
        save_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"saved -> {save_path}")
        return EXIT_MOVED

    if compare_path:
        before = json.loads(compare_path.read_text(encoding="utf-8"))
        verdict, lines = _compare(before, payload)
        for line in lines:
            print(line)
        print(
            {
                EXIT_MOVED: "MOVED.",
                EXIT_NO_MOVEMENT: "NO MOVEMENT.",
                EXIT_REGRESSED: "REGRESSED: do not merge.",
                EXIT_CANNOT_JUDGE: "CANNOT JUDGE.",
            }[verdict]
        )
        return verdict

    return EXIT_MOVED


if __name__ == "__main__":
    raise SystemExit(main())
