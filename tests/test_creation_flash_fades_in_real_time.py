"""The flash must last the same real time on every screen (C-1892, §6 定量)."""

from __future__ import annotations

import pytest

from sidra_ai.evals.flash_fades_in_real_time import (
    FLASH_PAGES,
    RATES,
    TOLERANCE,
    evaluate_flash_fades_in_real_time,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_flash_fades_in_real_time()


def test_every_flash_page_fades_on_the_clock(result):
    assert result.passed, "; ".join(result.failures)


def test_every_page_and_rate_was_measured(result):
    # One reading per rate per page, and every one of them checked: the
    # count is derived so a page that silently stopped being measured
    # cannot leave the total looking full.
    assert result.checks_total == result.checks_passed
    assert len(result.halves) == len(FLASH_PAGES)
    for line in result.halves:
        for hz in RATES:
            assert f"{hz}Hz" in line


def test_the_fast_screens_agree_with_the_slow_one(result):
    # The defect C-1892 fixed made the flash 2.4x shorter at 144Hz, which
    # is far outside the tolerance; pin that the tolerance is still the
    # kind of number that would have caught it.
    assert TOLERANCE < 0.5


def test_the_veil_is_drawn_not_just_declared(result):
    # Deleting the effect must not pass a test about the effect's length.
    assert not any("barely painted" in f for f in result.failures)
