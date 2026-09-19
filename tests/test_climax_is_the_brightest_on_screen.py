"""The painted climax, pinned (C-1978, §7 観察 6 / §43).

The judge reads pixels in a real browser. These tests hold the two things
a reading like that can quietly lose: the step it is measured against, and
the fact that the scene really is pinned while the world stays live.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.evals.canvas_matches_the_language_asked import TEMPLATE_ASKS
from sidra_ai.evals.climax_is_the_brightest_on_screen import (
    FRAMES,
    SAMPLES,
    STEP_LOG,
    evaluate_climax_is_the_brightest_on_screen,
    measure,
    step_of,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_step_is_the_one_the_research_names() -> None:
    """§43: Pelli-Robson drops contrast by 1/sqrt(2) between triplets."""
    assert STEP_LOG == 0.15
    assert SAMPLES % 2 == 1, "an even sample count has no median"


def test_the_step_is_read_against_the_brightest_act_before_it() -> None:
    """Not against the first act: adventure's cave is darker than its forest."""
    assert step_of([0.04, 0.01, 0.04]) == pytest.approx(0.0)
    assert step_of([0.01, 0.04, 0.04]) == pytest.approx(0.0)
    assert step_of([0.05, 0.10, 0.20]) == pytest.approx(0.301, abs=0.002)


def test_every_template_keeps_its_climax_on_screen() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_climax_is_the_brightest_on_screen()
    assert result.templates_whose_climax_reads == result.templates_total, result.failures


def test_the_acts_are_really_different_pictures() -> None:
    """A pinned scene that did not reach the paint would read three times the same."""
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = measure("puzzle")
    assert "err" not in seen, seen.get("err")
    assert len(set(seen["painted"])) == len(seen["painted"]), seen["painted"]
    assert len(seen["claim"]) == len(seen["painted"])
    assert FRAMES >= 100, "kaiju's waking scrim clears around frame 95"
    assert len(TEMPLATE_ASKS) == 10
