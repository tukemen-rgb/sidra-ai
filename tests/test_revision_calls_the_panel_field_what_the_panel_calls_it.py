"""C-1880: the revision answer uses the panel's own word for a panel row.

The page's tuning panel has a row labelled 「毎回ブリーフィングを見る」 and the
revision vocabulary called it 「ブリーフィング」. Those are different promises,
and the shorter one is wrong: the flag is not an on/off for the briefing
screen. The page shows the briefing on a first visit whatever the flag says
(`startscreen.py` needs `gateSeen()` to skip it, and `tuning.py`'s own comment
says so), so `False` means 「not every time」.

Measured before the fix: straight after making a game,
「さっきのゲームのブリーフィングをオフにして」 answered 「変更なし（すでにその設定
です）」 - to somebody who had just read the briefing.
"""

from __future__ import annotations

from sidra_ai.creation.games import _DIFFICULTY
from sidra_ai.creation.revise import CHANGEABLE, _flag_already_note
from sidra_ai.creation.tuning import BRIEF_LABEL, panel_schema
from sidra_ai.evals.revision_calls_the_panel_field_what_the_panel_calls_it import (
    evaluate_revision_calls_the_panel_field_what_the_panel_calls_it,
)


def _panel_label(key: str) -> str | None:
    schema = panel_schema(
        "racing", _DIFFICULTY["racing"], difficulty="normal", accent="#ff0000"
    )
    for field in schema["fields"]:
        if field["key"] == key:
            return field["label"]
    return None


def test_the_two_vocabularies_are_one_string() -> None:
    """Read off the live schema, not off a copy of the literal."""

    assert _panel_label("brief") == BRIEF_LABEL
    assert dict(CHANGEABLE)["brief"] == BRIEF_LABEL


def test_off_when_already_off_says_what_that_leaves_true() -> None:
    note = _flag_already_note({"brief": "off"}, {"brief": False})

    assert note, "the case this exists for produces nothing"
    assert "初回" in note, (
        "「already off」 without this is read as 「the screen is gone」, and the "
        "next first visit contradicts it"
    )
    assert BRIEF_LABEL in note


def test_the_note_stays_off_a_state_the_request_just_changed() -> None:
    """Turning it off when it was on is a change; 「切のままです」 would be false.

    Checked by calling the helper: the state is not reachable through the
    service, because a real change never takes the no-change branch the note
    lives in. Recorded as the weaker evidence it is.
    """

    assert _flag_already_note({"brief": "off"}, {"brief": True}) == ""


def test_the_note_is_not_printed_for_other_fields() -> None:
    assert _flag_already_note({"daily": "off"}, {"daily": False}) == ""
    assert _flag_already_note({}, {}) == ""


def test_turning_it_on_is_still_a_change() -> None:
    """The reading the fix must not break: 「on」 does mean every visit."""

    assert _flag_already_note({"brief": "on"}, {"brief": False}) == ""


def test_the_judge_agrees_and_says_so() -> None:
    result = evaluate_revision_calls_the_panel_field_what_the_panel_calls_it()

    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total == 6
