"""The shared juice fades on the clock, not the frame count (C-1898, §1)."""

from __future__ import annotations

import pytest

from sidra_ai.evals.juice_fades_in_real_time import (
    RATES,
    TOLERANCE,
    evaluate_juice_fades_in_real_time,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_juice_fades_in_real_time()


def test_the_juice_lasts_the_same_real_time_on_every_screen(result):
    assert result.passed, "; ".join(result.failures)


def test_both_halves_of_the_pair_were_read(result):
    # The shake multiplies and the particles subtract; a fix that reached
    # only one of them must not be able to pass.
    assert len(result.readings) == 2
    assert any(r.startswith("揺れ") for r in result.readings)
    assert any(r.startswith("粒子") for r in result.readings)
    assert result.checks_total == result.checks_passed


def test_every_rate_is_in_the_reading(result):
    for line in result.readings:
        for hz in RATES:
            assert f"{hz}Hz" in line


def test_the_tolerance_would_have_caught_the_defect():
    # C-1898 measured the shake at -50% (120Hz) and -58% (144Hz).
    assert TOLERANCE < 0.45
