"""The creature's size, as the frame has it (C-1980, §6 観察 1).

The judge reads painted pixels. These tests hold the number that was
chosen rather than measured, and the colour rule that lets the creature be
told apart from the city behind it.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.creation.themes import THEMES
from sidra_ai.evals.the_giant_does_not_fit_the_frame import (
    SCALE,
    _REPORT,
    evaluate_the_giant_does_not_fit_the_frame,
    fighting,
    read_theme,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_scale_is_a_chosen_number() -> None:
    """§6 gives no size; 10x is an order of magnitude against a measured 30x."""
    assert SCALE == 10.0


def test_the_colour_match_is_exact() -> None:
    """A tolerance counted the city as the creature.

    Measured: with +-6 per channel, the paper theme read 30.7% creature and
    965 edge pixels, because a light theme's scene transform barely moves
    that hue. Exact matching put all four themes on 8.8-8.9% and 112.
    """
    assert "d[i] === want[0]" in _REPORT
    assert "Math.abs(d[i]" not in _REPORT


def test_every_theme_paints_a_creature_too_big_for_the_frame() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_the_giant_does_not_fit_the_frame()
    assert result.checks_passed == result.checks_total, result.failures
    assert result.checks_total == len(THEMES) * 3


def test_only_the_fight_is_counted() -> None:
    """Before the fight the creature is behind its own scrim."""
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = read_theme("gameyard")
    assert "err" not in seen, seen.get("err")
    assert [f["state"] for f in seen["frames"]][0] != "fight", seen["frames"][0]
    assert len(fighting(seen)) >= 2, seen["frames"]
