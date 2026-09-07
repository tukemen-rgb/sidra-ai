"""One noun, three answers (C-1504).

「企画一式」 was not in the project vocabulary and 「ゲーム」 was in the game
vocabulary, so the same noun phrase resolved three different ways:

* 「ゲームの企画一式を作って」 → a fishing GAME titled 「ゲームの企画一式」;
* 「企画一式を作って」        → declined as unknown;
* 「ゲームを企画から作って」  → the project, correctly.

Adding 「企画一式」/「企画書一式」 to the project words makes the first two
agree with the third. What must NOT move is C-1263's line: a single 企画 or
計画 document is still one document, and 「ゲームの企画を作って」 is still a
game request. That boundary is half of these tests, because widening the
vocabulary is exactly how it would be crossed by accident.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import detect_creation_intent


def kind_of(text: str) -> str:
    return detect_creation_intent(text).kind.value


# ------------------------------------------------------------- the defect


@pytest.mark.parametrize(
    "ask",
    [
        "ゲームの企画一式を作って",
        "企画一式を作って",
        "ゲームの企画書一式を作って",
        "企画書一式を作って",
    ],
)
def test_a_full_set_is_a_project(ask: str) -> None:
    assert kind_of(ask) == "project"


def test_the_three_phrasings_now_agree() -> None:
    """The point of the item: one noun, one answer."""

    asked = [
        "ゲームの企画一式を作って",
        "企画一式を作って",
        "ゲームを企画から作って",
    ]
    assert {kind_of(text) for text in asked} == {"project"}


def test_both_spellings_are_listed_because_neither_contains_the_other() -> None:
    """「企画書一式」 is not a superstring of 「企画一式」.

    Written as a test rather than a comment because a later tidy-up that
    dropped one entry as "redundant" would pass everything else.
    """

    assert "企画一式" not in "企画書一式"
    assert kind_of("企画書一式を作って") == "project"


# ------------------------------------------- C-1263's line, still standing


@pytest.mark.parametrize(
    "ask, kind",
    [
        # A single planning document is still one document, and with a
        # subject attached it is still a game request.
        ("ゲームの企画を作って", "game"),
        ("ゲームの計画を作って", "game"),
        ("ゲームの企画書を作って", "game"),
        # ...and on its own it is still declined rather than guessed at.
        ("企画を作って", "unknown"),
        ("計画を作って", "unknown"),
        ("企画書を作って", "unknown"),
    ],
)
def test_a_single_planning_document_is_unchanged(ask: str, kind: str) -> None:
    assert kind_of(ask) == kind


@pytest.mark.parametrize(
    "ask",
    ["ゲームを作って", "レースゲームを作って", "パズルゲームを作って"],
)
def test_plain_game_requests_are_unchanged(ask: str) -> None:
    assert kind_of(ask) == "game"


@pytest.mark.parametrize(
    "ask",
    ["ゲームを一通り作って", "ゲームの制作一式を作って", "ゲームを企画から作って"],
)
def test_the_project_words_that_already_worked_still_do(ask: str) -> None:
    assert kind_of(ask) == "project"


# ------------------------------------------------------- what it delivers


def test_the_project_actually_runs_rather_than_shipping_a_game() -> None:
    """Routing is not the deliverable - the stages are.

    The reported symptom was a playable fishing page arriving under a
    project's title, so this drives the real generator and checks that what
    comes back is a project.
    """

    import tempfile

    from sidra_ai.creation.project_job import build_project_generator

    ask = "ゲームの企画一式を作って"
    with tempfile.TemporaryDirectory() as folder:
        outcome = build_project_generator(folder)(ask, detect_creation_intent(ask))
        assert outcome.handled
        assert outcome.kind.value == "project"
