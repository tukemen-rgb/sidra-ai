"""C-1404 (b): every difficulty rung of the race can be finished.

Easy's three laps took ~64 seconds against the sixty-second round clock, so
the gentlest setting was the one nobody finishes. The decision keeps the
pace ladder and gives easy two laps: difficulty scales scope, not only
speed. Pinned by driving the real pages, because a lap constant is exactly
the kind of thing a source check would wave through.

C-1625 asked the second question of the same runs. "Every rung finishes"
was true while the ladder ran backwards: normal reached the goal at 51.1s
and hard at 41.0s, because the top rung ran 23% faster over the same three
laps, so raising the difficulty made the course SHORTER and left the
harshest setting the most room against the only way this template can be
lost. C-1404's own principle - scope, not only speed - applied to the top
rung as well: hard runs four laps and finishes at 57.3s.

And the title screen said 「3 周」 on every rung, including the easy one
that has run two laps since C-1404. The objective on the screen a player
cannot get past without reading was wrong for the gentlest setting.
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
    assert RACING_LAPS == {"easy": 2, "normal": 3, "hard": 4}


def test_each_rung_bakes_its_own_lap_count_into_the_page() -> None:
    for rung, laps in RACING_LAPS.items():
        page = generate_game("レースゲームを作って", difficulty=rung).html
        assert f"LAPS={laps}," in page, rung
        assert "LAPS_TOKEN" not in page, "the token must not leak to the page"


def test_the_scope_grows_with_the_pace() -> None:
    """The arithmetic behind C-1625, before anything is driven.

    A rung is a distance and a speed. If the speed rises and the distance
    does not, the course gets shorter - which is what happened between
    normal and hard, and what turns the difficulty dial into a discount on
    the only losing condition this template has.
    """

    clean = {
        rung: RACING_LAPS[rung] / RACING_DIFFICULTY[rung][0]
        for rung in ("easy", "normal", "hard")
    }

    assert clean["easy"] < clean["normal"] < clean["hard"], clean


@pytest.fixture(scope="module")
def driven():
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the pages")
    from sidra_ai.evals.race_rungs import evaluate_race_rungs

    return evaluate_race_rungs()


def test_every_rung_is_finishable_when_driven(driven) -> None:
    assert driven.failures == ()
    assert driven.finishable == driven.rungs == 3


def test_a_harder_rung_never_finishes_sooner(driven) -> None:
    """Driven, not derived: the clean-lap arithmetic above says nothing
    about what the obstacles and the road's curve do to a real run."""

    assert [rung for rung, _ in driven.times] == ["easy", "normal", "hard"]
    spent = [ms for _, ms in driven.times]
    assert spent == sorted(spent), driven.times
    assert driven.ladder


def test_the_hardest_rung_is_the_one_with_the_least_room(driven) -> None:
    """The property in the player's terms: on hard, the weakest possible
    drive only just gets home."""

    room = {rung: 60000 - ms for rung, ms in driven.times}

    assert room["hard"] == min(room.values()), room
    assert room["hard"] > 0, "the floor of play must still finish every rung"


def test_a_rung_that_never_finished_is_not_ranked() -> None:
    """"Slower" and "did not arrive" are different readings, and only the
    first belongs on a ladder."""

    from sidra_ai.evals.race_rungs import RaceRungsResult

    hole = RaceRungsResult(2, 3, (), (("easy", 45150), ("normal", 51117)))
    assert not hole.ladder

    failed = RaceRungsResult(
        2, 3, ("hard: race at 60017ms",),
        (("easy", 45150), ("normal", 51117), ("hard", 60017)),
    )
    assert not failed.ladder


def test_a_backwards_ladder_is_not_a_ladder() -> None:
    """The reading C-1625 exists for, as a unit: three rungs that all
    finished, in the order they are offered, with the hardest home first."""

    from sidra_ai.evals.race_rungs import RaceRungsResult

    backwards = RaceRungsResult(
        3, 3, (), (("easy", 45150), ("normal", 51117), ("hard", 41000))
    )
    assert not backwards.ladder

    forwards = RaceRungsResult(
        3, 3, (), (("easy", 45150), ("normal", 51117), ("hard", 57300))
    )
    assert forwards.ladder


def test_the_title_screen_names_the_laps_this_rung_actually_runs() -> None:
    """C-1625: it said 「3 周」 on easy, which has run two laps since C-1404.

    Read off the built page for every rung, against the same page's own
    ``LAPS`` rather than against the table, so the briefing and the race
    cannot drift apart the way they did.
    """

    import re

    for rung, laps in RACING_LAPS.items():
        page = generate_game("レースゲームを作って", difficulty=rung).html
        baked = re.search(r"LAPS=(\d+),", page)

        assert baked and int(baked.group(1)) == laps, rung
        assert f"コースに沿って {laps} 周を走り切り" in page, rung
        assert "LAPS_TOKEN" not in page, "the token must not leak to the page"


def test_the_instruction_line_names_every_rung_by_its_laps() -> None:
    from sidra_ai.creation.racing import RACING_HOW

    for label, laps in (("やさしい", 2), ("ふつう", 3), ("むずかしい", 4)):
        assert f"{label}は {laps} 周" in RACING_HOW, label
