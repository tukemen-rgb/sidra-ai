"""A generated picture advances by time, not by refresh rate (C-1900)."""

from __future__ import annotations

import pytest

from sidra_ai.creation.art import _BODIES
from sidra_ai.evals.art_advances_in_real_time import (
    MEASURE,
    MEASURE_WHY,
    RATES,
    TOLERANCE,
    evaluate_art_advances_in_real_time,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_art_advances_in_real_time()


def test_every_pattern_draws_the_same_picture_on_every_screen(result):
    assert result.passed, "; ".join(result.failures)


def test_every_pattern_was_measured(result):
    assert len(result.readings) == len(_BODIES)
    assert result.checks_total == result.checks_passed


def test_each_pattern_has_a_measure_and_a_reason():
    # The two patterns are judged differently on purpose - orbits by its
    # frame, flow by how far the pen travelled - so the choice has to be
    # written down rather than inferred.
    assert set(MEASURE) == set(_BODIES)
    assert set(MEASURE_WHY) == set(MEASURE)
    assert set(MEASURE.values()) <= {"frame", "path"}


def test_the_tolerance_would_have_caught_the_defect():
    # Unfixed, 144Hz advanced 2.4x as far as 60Hz.
    assert TOLERANCE < 0.2
    assert 60 in RATES and len([hz for hz in RATES if hz > 60]) >= 2
