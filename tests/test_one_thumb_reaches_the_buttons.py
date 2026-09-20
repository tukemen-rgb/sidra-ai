"""One thumb, on the screen (C-1982, §8 事実 5/8).

The judge drives two pages with touch pointers only. These tests hold the
two properties that make the reading mean anything: no keyboard is used,
and the button pressed sits on the opposite side from where the player
ends up - so "followed the finger" cannot pass for "pressed the button".
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.evals.one_thumb_reaches_the_buttons import (
    ASKS,
    MOVED,
    _REPORT,
    evaluate_one_thumb_reaches_the_buttons,
    read_template,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_probe_never_builds_a_key() -> None:
    """A thumb is the whole point: one KeyboardEvent would hollow it out."""
    assert "KeyboardEvent" not in _REPORT, "the probe must not build one, or mention one"
    assert "pointerType: 'touch'" in _REPORT


def test_the_button_is_on_the_far_side_from_the_movement() -> None:
    """The pad's right button lives on the left of the canvas.

    Measured: it sits at x=283.5 of a 720px canvas while the press takes
    catch's tray from 379 to 683. A player that merely eased toward the
    finger would have gone the other way.
    """
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = read_template("catch")
    assert "err" not in seen, seen.get("err")
    assert seen["buttonX"] < seen["middle"], seen
    assert seen["after"] - seen["before"] >= MOVED, seen


def test_one_thumb_can_play_both_templates() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_one_thumb_reaches_the_buttons()
    assert result.checks_passed == result.checks_total, result.failures
    assert result.checks_total == len(ASKS) * 4
