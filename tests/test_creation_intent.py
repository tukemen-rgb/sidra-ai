"""Which messages count as "make me something", and which stay questions.

The failure this file guards against is one-directional. Missing a creation
request costs an ordinary answer; misreading a question as a creation request
takes the question path away from someone who wanted it. So the negative
cases below are the load-bearing ones, and they are written from the shapes
an operator actually types rather than from the detector's own tables.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import CreationKind, detect_creation_intent


@pytest.mark.parametrize(
    "message, kind",
    [
        ("釣りゲームを作って", CreationKind.GAME),
        ("ミニゲームを生成してください", CreationKind.GAME),
        ("デッキを作って", CreationKind.DECK),
        ("営業用のスライドを作成して", CreationKind.DECK),
        ("週報のレポートを書いて", CreationKind.DOCUMENT),
        ("make me a fishing game", CreationKind.GAME),
        ("build a pitch deck", CreationKind.DECK),
    ],
)
def test_a_request_to_make_something_routes(message: str, kind: CreationKind) -> None:
    intent = detect_creation_intent(message)

    assert intent.is_creation
    assert intent.kind is kind
    assert intent.routes


@pytest.mark.parametrize(
    "message",
    [
        "ゲームの作り方を教えて",
        "デッキはどうやって作りますか",
        "ミニゲームを作る方法は",
        "how do I build a game",
        "what is a pitch deck",
    ],
)
def test_asking_how_to_make_something_stays_a_question(message: str) -> None:
    """The operative verb in Japanese comes last, and here it is the asking one.

    This is the case that would quietly break Q&A: every one of these
    contains an artifact word, and most contain a making-verb too.
    """

    intent = detect_creation_intent(message)

    assert not intent.is_creation
    assert not intent.routes


@pytest.mark.parametrize(
    "message",
    [
        "SIDRA は取得した文書をどう扱いますか",
        "制作会社との契約はどうなっていますか",
        "この作業の担当者は誰ですか",
        "ゲーム業界の市場規模は",
        "",
        "   ",
    ],
)
def test_ordinary_questions_are_not_creation(message: str) -> None:
    """Including the near misses: 制作会社, 作業, and a bare artifact word.

    A stem-based detector matching "作" would route the middle two, which is
    why the table holds surface forms.
    """

    assert not detect_creation_intent(message).is_creation


def test_making_something_unnamed_is_recognised_but_not_routed() -> None:
    """"作って" with no artifact names nothing this project can build.

    Recognised so the gap is visible, unrouted so no generator gets to guess
    what the operator meant.
    """

    intent = detect_creation_intent("いい感じのやつを作って")

    assert intent.is_creation
    assert intent.kind is CreationKind.UNKNOWN
    assert not intent.routes


def test_the_head_noun_decides_the_kind() -> None:
    """"ゲームの資料" is a document about a game, not a game."""

    assert detect_creation_intent("ゲームの資料を作って").kind is CreationKind.DECK
    assert detect_creation_intent("資料に載せるゲームを作って").kind is CreationKind.GAME


def test_width_and_case_do_not_change_the_decision() -> None:
    """A Japanese IME emits full-width Latin; it must classify the same."""

    assert detect_creation_intent("ＭＡＫＥ　Ａ　ＧＡＭＥ").kind is CreationKind.GAME


def test_evidence_is_drawn_from_the_table_not_the_message() -> None:
    """Evidence is logged, so it must never carry operator text.

    A secret pasted into a request would otherwise reach the audit trail
    through the one field that describes why routing happened.
    """

    intent = detect_creation_intent("ghp_" + "0" * 36 + " で釣りゲームを作って")

    assert intent.routes
    assert all("ghp_" not in item for item in intent.evidence)
    assert set(intent.evidence) <= {"作って", "ゲーム", "釣りゲーム"}
