"""The creator-facing questions are a visible subset, not a second headline.

"SIDRA answers 10 of 27" is a statement about operators asking about the
business. The direction this work was pointed at is narrower and more
concrete: can it answer the person who is building a game and putting it on
GAMEYARD - will my Unity build run, how big can the zip be, can I edit what I
posted. That subset can be flat while the headline improves, and nobody would
see it.

So these questions stay in the headline counts - they are ordinary questions
about other people's repositories and removing them would be hiding the hard
ones - and are tallied again on their own line. These tests hold both halves:
the subset is really a subset, and it is really reported.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS, OutcomeQuestion

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_measure_outcomes():
    spec = importlib.util.spec_from_file_location(
        "measure_outcomes_game_under_test",
        REPO_ROOT / "scripts" / "measure_outcomes.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mo():
    return _load_measure_outcomes()


ANSWER = "投稿できる形式はこの一文が定めている固有の言い回しである"
OTHER = "運営の都合について書かれた別の固有の一文である"


def _corpus(tmp_path: Path):
    repo = tmp_path / "outside"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "submit.md").write_text(
        f"# 投稿\n\n投稿の作法について。{ANSWER}\n", encoding="utf-8"
    )
    (repo / "docs" / "ops.md").write_text(
        f"# 運営\n\n運営の段取りについて。{OTHER}\n", encoding="utf-8"
    )
    return [("other/outside", repo)]


CREATOR_QUESTION = OutcomeQuestion(
    name="fixture-gp",
    question="投稿の作法について教えてください",
    answer_marker=ANSWER,
    repository="other/outside",
    game_production=True,
)

OPERATOR_QUESTION = OutcomeQuestion(
    name="fixture-ops",
    question="運営の段取りについて教えてください",
    answer_marker=OTHER,
    repository="other/outside",
)


def _measure(mo, questions, targets):
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


def test_creator_questions_stay_in_the_headline(mo, tmp_path) -> None:
    """Unlike the self-grounded tier, these count where every question counts.

    Lifting them out would make the headline a measurement of the easy half.
    """

    targets = _corpus(tmp_path)
    result = _measure(mo, [CREATOR_QUESTION, OPERATOR_QUESTION], targets)

    assert result["questions"] == 2
    assert result["scored"] == 2
    assert result["answered"] == 2


def test_the_subset_is_reported_on_its_own_line(mo, tmp_path) -> None:
    targets = _corpus(tmp_path)
    result = _measure(mo, [CREATOR_QUESTION, OPERATOR_QUESTION], targets)

    block = result["game_production"]
    assert block["questions"] == 1
    assert block["scored"] == 1
    assert block["answered"] == 1
    assert block["rate"] == 1.0
    assert block["misses"] == []


def test_a_creator_question_that_misses_is_named(mo) -> None:
    """The point of the line is to show which creator questions fail.

    Scored from rows directly: a fixture corpus small enough to control is
    also small enough that every question retrieves something, so a real
    miss cannot be staged in it.
    """

    missed = OutcomeQuestion(
        name="fixture-gp-miss",
        question="見つからない質問",
        answer_marker=ANSWER,
        repository="other/outside",
        game_production=True,
    )
    rows = [
        {"name": "fixture-gp", "status": "hit"},
        {"name": "fixture-gp-miss", "status": "miss"},
        {"name": "fixture-ops", "status": "hit"},
        {"name": "fixture-gp-ungrounded", "status": "ungrounded"},
    ]
    headline = (
        CREATOR_QUESTION,
        missed,
        OPERATOR_QUESTION,
        OutcomeQuestion(
            name="fixture-gp-ungrounded",
            question="根拠が無い質問",
            answer_marker="どこにも無い一文",
            repository="other/outside",
            game_production=True,
        ),
    )

    block = mo._tally_game_production(rows, headline)

    assert block["questions"] == 3, "the ungrounded one is still a question"
    assert block["scored"] == 2, "but it cannot be scored"
    assert block["answered"] == 1
    assert block["misses"] == ["fixture-gp-miss"]


def test_the_shipped_set_has_a_creator_subset_and_it_is_not_everything(mo) -> None:
    """A subset that swallowed the whole set would stop being a subset."""

    creator = [q for q in OUTCOME_QUESTIONS if q.game_production]
    assert creator, "the creator-facing questions are missing"
    assert len(creator) < len(OUTCOME_QUESTIONS)
    assert all(not q.self_grounded for q in creator), (
        "a creator question is answered by someone else's repository, "
        "not by ours"
    )
