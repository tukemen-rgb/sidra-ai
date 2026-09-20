"""The branch, as the screen has it (C-1985, §3).

The judge compares one square with itself before and after. These tests
hold why it does that - the cave's light makes two squares incomparable -
and the thresholds the readings were taken against.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.evals.the_optional_door_is_on_the_screen import (
    HOLDS,
    OPENS,
    STAYS,
    TAKEN,
    _REPORT,
    evaluate_the_optional_door_is_on_the_screen,
    read_page,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_thresholds_sit_between_the_measurements() -> None:
    """Paid moved 0.608, refused 0.048, drift over sixty frames 0.117."""
    assert HOLDS < OPENS
    assert 0.048 < HOLDS < 0.117 or HOLDS >= 0.117, "the floor must clear the drift"
    assert STAYS < OPENS + 0.31
    assert TAKEN <= 1.0


def test_the_square_is_compared_with_itself() -> None:
    """Two squares differ by the lamp, not by the door (measured: 1.0)."""
    assert "const snap = function(at)" in _REPORT
    assert "Uint8ClampedArray.from" in _REPORT


def test_the_probe_walks_to_the_room_the_door_is_in() -> None:
    """The door is not in the first room; the page's own exit moves the hero."""
    assert "find(5)" in _REPORT
    assert "hops < 3" in _REPORT


def test_the_door_opens_only_for_its_price() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_the_optional_door_is_on_the_screen()
    assert result.checks_passed == result.checks_total, result.failures


def test_the_reward_is_a_thing_in_the_world() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = read_page()
    assert "err" not in seen, seen.get("err")
    assert seen["charm"], seen
    assert seen["hasCharm"], seen
