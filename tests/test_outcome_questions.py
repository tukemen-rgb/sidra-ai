"""Guards on the outcome question set itself.

The outcome measurement is only worth anything if its questions stay grounded
in repositories we do not write. These tests cannot check that from inside the
repository -- the other four are not present in CI -- so they check the
properties that *can* be checked here: that the set stays well formed, that no
question smuggles its own answer into the prompt, and that no question is
answered by sidra-ai's own documentation.

The corpus-grounding check lives in ``scripts/measure_outcomes.py``, which
fails when a marker is absent from the checked-out repositories.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.outcome_questions import (
    OUTCOME_QUESTIONS,
    OutcomeQuestion,
    questions_by_repository,
)

ALLOWED_REPOSITORIES = {
    "tukemen-rgb/site",
    "tukemen-rgb/creater-yard",
    "tukemen-rgb/Fg",
    "tukemen-rgb/marketing",
    "tukemen-rgb/sidra-ai",
}


def test_the_set_is_not_empty() -> None:
    assert OUTCOME_QUESTIONS


@pytest.mark.parametrize("question", OUTCOME_QUESTIONS, ids=lambda q: q.name)
def test_question_names_are_unique_and_populated(question: OutcomeQuestion) -> None:
    assert question.name
    assert question.question
    assert question.answer_marker
    assert question.tier in {"direct", "paraphrase"}


def test_names_do_not_collide() -> None:
    names = [question.name for question in OUTCOME_QUESTIONS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("question", OUTCOME_QUESTIONS, ids=lambda q: q.name)
def test_question_targets_an_allowlisted_repository(question: OutcomeQuestion) -> None:
    assert question.repository in ALLOWED_REPOSITORIES


@pytest.mark.parametrize("question", OUTCOME_QUESTIONS, ids=lambda q: q.name)
def test_question_does_not_contain_its_own_answer(question: OutcomeQuestion) -> None:
    """A question that quotes its marker measures string equality, not search.

    Retrieval would then be scored on a term the asker already supplied, which
    is exactly the self-referential failure this whole file exists to prevent.
    """

    assert question.answer_marker not in question.question


@pytest.mark.parametrize(
    "question",
    [q for q in OUTCOME_QUESTIONS if q.tier == "paraphrase"],
    ids=lambda q: q.name,
)
def test_paraphrase_questions_avoid_the_marker_vocabulary(
    question: OutcomeQuestion,
) -> None:
    """A paraphrase must not reuse long runs of the answer's own wording.

    Sharing a four-character run in Japanese is usually a real content word.
    If a 'paraphrase' reuses one, it is a direct question wearing a label, and
    the paraphrase tier stops reporting what it claims to report.
    """

    marker = question.answer_marker
    runs = {marker[i:i + 4] for i in range(len(marker) - 3)}
    overlapping = sorted(run for run in runs if run in question.question)
    assert not overlapping, (
        f"{question.name} reuses the marker's wording: {overlapping}"
    )


def test_outcome_questions_are_not_answered_by_our_own_repository() -> None:
    """Grounding the set in sidra-ai would make it self-referential.

    sidra-ai is the one repository whose documents this project writes. A
    question answered from it would be scored against our own prose, which is
    the inside number the outcome measurement exists to escape.
    """

    self_grounded = [
        question.name for question in OUTCOME_QUESTIONS
        if question.repository == "tukemen-rgb/sidra-ai"
    ]
    assert not self_grounded, (
        "outcome questions must be answered by repositories this project does "
        f"not author; found {self_grounded}"
    )


def test_both_tiers_are_represented() -> None:
    tiers = {question.tier for question in OUTCOME_QUESTIONS}
    assert tiers == {"direct", "paraphrase"}


def test_grouping_covers_every_question() -> None:
    grouped = questions_by_repository()
    assert sum(len(items) for items in grouped.values()) == len(OUTCOME_QUESTIONS)
