"""C-1404 (b): every difficulty rung of the race can be finished.

Easy's three laps took ~64 seconds against the sixty-second round clock, so
the gentlest setting was the one nobody finishes. The decision keeps the
pace ladder and gives easy two laps: difficulty scales scope, not only
speed. Pinned by driving the real pages, because a lap constant is exactly
the kind of thing a source check would wave through.
"""

from __future__ import annotations

import shutil

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.racing import RACING_DIFFICULTY, RACING_LAPS


def test_the_ladder_keeps_its_paces_and_easy_runs_two_laps() -> None:
    # The decision was (b), not (a): the pace numbers are the losing path's
    # and the judges' ground, so they must not drift as a side effect.
    assert RACING_DIFFICULTY["easy"][0] == 2.4
    assert RACING_LAPS == {"easy": 2, "normal": 3, "hard": 3}


def test_each_rung_bakes_its_own_lap_count_into_the_page() -> None:
    for rung, laps in RACING_LAPS.items():
        page = generate_game("レースゲームを作って", difficulty=rung).html
        assert f"LAPS={laps}," in page, rung
        assert "LAPS_TOKEN" not in page, "the token must not leak to the page"


def test_every_rung_is_finishable_when_driven() -> None:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the pages")
    from sidra_ai.evals.race_rungs import evaluate_race_rungs

    result = evaluate_race_rungs()
    assert result.failures == ()
    assert result.finishable == result.rungs == 3
