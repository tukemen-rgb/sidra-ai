"""The shrine's payment, as the screen shows it (C-1984, §5).

The judge drives one page. These tests hold the size of a heart, the band
the hearts are counted in, and the fact that the probe swings rather than
steps - the shrine answers a sword, not a footfall.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.evals.the_shrine_pays_in_hearts import (
    BAND,
    HEART,
    _REPORT,
    evaluate_the_shrine_pays_in_hearts,
    read_page,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_a_heart_is_the_size_the_hud_draws() -> None:
    """adventure paints fillRect(OX + i*18, 2, 14, 10): 140 pixels."""
    assert HEART == 14 * 10
    assert BAND == 14, "the band must cover the row and stop above the world"


def test_the_probe_swings_at_the_shrine() -> None:
    """Standing on the tile does nothing; the tile answers the sword."""
    assert "hero.dir = 1" in _REPORT
    assert "grid[y][x] === 9" in _REPORT
    assert "probeKey(' ')" in _REPORT


def test_the_shrine_pays_and_refuses_on_the_screen() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_the_shrine_pays_in_hearts()
    assert result.checks_passed == result.checks_total, result.failures


def test_the_ceiling_keeps_the_gems() -> None:
    """C-1674: a sink that returns nothing must not take payment."""
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = read_page()
    assert "err" not in seen, seen.get("err")
    assert seen["gemsAfterFull"] == 3, seen
    assert seen["fullDelta"] == 0, seen
