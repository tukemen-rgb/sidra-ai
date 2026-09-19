"""The hit, as the screen has it (C-1979, §1).

The judge opens one page. These tests hold the thresholds, keep the
measurement on the still screen where it is honest, and cover a second
template the judge does not open.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.juice_reaches_the_screen import (
    GRAIN_FACTOR,
    MOVED_PX,
    WEIGHT,
    _REPORT,
    _open,
    evaluate_juice_reaches_the_screen,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_thresholds_are_the_ones_the_readings_were_taken_against() -> None:
    assert WEIGHT == 9
    assert MOVED_PX == 1.0
    assert GRAIN_FACTOR == 3.0


def test_the_shake_is_read_before_the_round_starts() -> None:
    """A live catch round calls shake(5) on every dropped fruit.

    Measured while writing this: SHAKE was still 0.584 after 162 frames,
    because the game kept refreshing it. Reading the settle inside the
    round would call that a stage that never comes home.
    """
    assert _REPORT.index("shake(WEIGHT_TOKEN)") < _REPORT.index("probeKey(' ')")
    assert _REPORT.index("out.settled") < _REPORT.index("probeKey(' ')")


def test_the_screen_keeps_the_hit() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_juice_reaches_the_screen()
    assert result.checks_passed == result.checks_total, result.failures


def test_a_second_template_moves_and_comes_home() -> None:
    """The judge opens catch; the shake belongs to every template."""
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = _open(generate_game("make a shooting game about an owl").html, reduced=False)
    assert "err" not in seen, seen.get("err")
    assert seen["far"] >= MOVED_PX, seen
    assert seen["settled"] == seen["rest"], seen
    assert seen["amount"] == 0, seen
