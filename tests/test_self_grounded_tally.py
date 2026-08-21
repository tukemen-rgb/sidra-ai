"""A self-grounded question must be invisible to the headline numbers.

The 2026-08-20 approval was for a *separate* tally, and the whole value of
that word is arithmetic: `answerable_total`, the two tiers, MRR and
discrimination have to read exactly the same whether or not sidra-ai-grounded
questions exist. Otherwise the project has quietly started scoring itself
against its own prose, which is the failure the outcome set was built to
avoid, and the headline would drift for a reason no reader could see.

These tests hold that arithmetic rather than trusting the code to keep
honouring it. The easy mistakes are all ways of half-doing it:

* counting self questions in the denominator "because they were measured";
* leaving their markers in the foreign-marker set, which moves discrimination
  for the questions that were already there without touching any counter that
  looks like it changed;
* flagging an ordinary question to lift it out of a denominator it was
  failing in.

Each of those is checked by running the real measurement twice - once with
the self questions present and once with them removed - and demanding the
headline block be identical.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS, OutcomeQuestion

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_measure_outcomes():
    spec = importlib.util.spec_from_file_location(
        "measure_outcomes_under_test", REPO_ROOT / "scripts" / "measure_outcomes.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mo():
    return _load_measure_outcomes()


HEADLINE_KEYS = (
    "questions",
    "scored",
    "answered",
    "answerable_rate",
    "mrr",
    "by_tier",
    "control_hits",
    "control_rate",
    "discrimination",
    "ungrounded",
    "rows",
)


def _corpus(mo, tmp_path: Path):
    """A two-repository corpus: one outside repository plus sidra-ai's docs.

    Small and hand-built on purpose - this test is about the bookkeeping, not
    about retrieval quality, and a fixture corpus keeps it from depending on
    checkouts that belong to other people.
    """

    outside = tmp_path / "outside"
    (outside / "docs").mkdir(parents=True)
    (outside / "docs" / "policy.md").write_text(
        "# 方針\n\n" + "外部リポジトリの方針を示す固有の一文である。\n" * 3,
        encoding="utf-8",
    )
    selfrepo = tmp_path / "selfrepo"
    (selfrepo / "docs").mkdir(parents=True)
    # The self document deliberately repeats the outside question's wording
    # as well as carrying the self marker. That makes it rank for the outside
    # question, which is the only way the foreign-marker set can be caught
    # doing something: if self markers are left in it, the outside question
    # starts counting as a control hit and discrimination moves. A fixture
    # where the two documents never compete would let that bug through while
    # every counter still looked untouched.
    (selfrepo / "docs" / "SECURITY.md").write_text(
        "# Security\n\n"
        "外部の方針はどこに書かれていますか。方針の所在についての節である。\n\n"
        "There is no token scope to misconfigure into a write.\n",
        encoding="utf-8",
    )
    return [
        ("other/outside", outside),
        ("tukemen-rgb/sidra-ai", selfrepo),
    ]


OUTSIDE_QUESTION = OutcomeQuestion(
    name="fixture-outside",
    question="外部の方針はどこに書かれていますか",
    answer_marker="外部リポジトリの方針を示す固有の一文である",
    repository="other/outside",
)

SELF_QUESTION = OutcomeQuestion(
    name="fixture-self",
    question="Can SIDRA modify a repository, or only read from it?",
    answer_marker="There is no token scope to misconfigure into a write",
    repository="tukemen-rgb/sidra-ai",
    self_grounded=True,
)


def _measure(mo, questions, targets):
    """Run the real measurement over a substituted question set."""

    original = mo.OUTCOME_QUESTIONS
    mo.OUTCOME_QUESTIONS = tuple(questions)
    try:
        gate = mo.SecurityGate(
            mo.GatePolicy(), allowed_repositories=[name for name, _ in targets]
        )
        store = mo.DocumentStore(gate)
        mo.ingest(targets, store, gate)
        return mo.measure_answerable(mo.BM25Retriever(store), targets)
    finally:
        mo.OUTCOME_QUESTIONS = original


def test_adding_a_self_question_moves_no_headline_number(mo, tmp_path) -> None:
    targets = _corpus(mo, tmp_path)

    without = _measure(mo, [OUTSIDE_QUESTION], targets)
    with_self = _measure(mo, [OUTSIDE_QUESTION, SELF_QUESTION], targets)

    for key in HEADLINE_KEYS:
        assert with_self[key] == without[key], (
            f"adding a self-grounded question changed the headline key {key!r}: "
            f"{without[key]!r} -> {with_self[key]!r}"
        )


def test_the_self_question_is_still_measured(mo, tmp_path) -> None:
    """Excluded from the headline is not the same as ignored.

    A separate tally that silently reported nothing would satisfy the test
    above while throwing the measurement away.
    """

    targets = _corpus(mo, tmp_path)
    with_self = _measure(mo, [OUTSIDE_QUESTION, SELF_QUESTION], targets)

    block = with_self["self_grounded"]
    assert block["questions"] == 1
    assert block["scored"] == 1, "the marker must be verified against the corpus"
    assert block["rows"][0]["name"] == "fixture-self"
    assert block["rows"][0]["status"] in {"hit", "miss"}
    assert block["ungrounded"] == []


def test_a_self_question_with_no_evidence_is_ungrounded_not_answered(
    mo, tmp_path
) -> None:
    """The marker check applies to the self tally too.

    Without it, the one tier scored against our own prose would be the tier
    where a question could pass by being written rather than by being
    answered.
    """

    targets = _corpus(mo, tmp_path)
    invented = OutcomeQuestion(
        name="fixture-self-invented",
        question="Does SIDRA do a thing nobody wrote down?",
        answer_marker="この文はどのリポジトリにも存在しない",
        repository="tukemen-rgb/sidra-ai",
        self_grounded=True,
    )

    result = _measure(mo, [OUTSIDE_QUESTION, invented], targets)

    block = result["self_grounded"]
    assert block["ungrounded"] == ["fixture-self-invented"]
    assert block["scored"] == 0
    assert block["answered"] == 0
    assert block["rate"] == 0.0


def test_the_shipped_set_keeps_the_two_apart(mo) -> None:
    """The real question set, not a fixture: the counts must not overlap."""

    headline = [q for q in OUTCOME_QUESTIONS if not q.self_grounded]
    selves = [q for q in OUTCOME_QUESTIONS if q.self_grounded]

    assert selves, "the approved self-grounded questions are missing"
    assert all(q.repository == "tukemen-rgb/sidra-ai" for q in selves)
    assert all(q.repository != "tukemen-rgb/sidra-ai" for q in headline)
    assert len(headline) + len(selves) == len(OUTCOME_QUESTIONS)
