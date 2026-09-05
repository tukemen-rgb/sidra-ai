"""C-1424: the instrument that can lose an adventure.

C-1423 could not measure the loss line because nothing had ever produced a
loss. The hero wakes at tile (2, 4) and the way out is (19, 4) - the same
row - but grass sits on that row and a pond spans columns 9-11 across rows
4 and 5. A pond cannot be cut, so the route out goes *around*, and no held
direction finds it.

The surprise worth keeping: letting the route run *through* the grass,
because the hero can cut it, is worse than going around. Cutting is slow -
the swing has a cooldown and has to be aimed - so a path counting on it
stalls with the hero pushing at a tile that is still solid.
"""

from __future__ import annotations

import shutil

import pytest

from sidra_ai.evals.adventure_losable import drive


@pytest.fixture(scope="module")
def path_drive():
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    return drive(mode="path")


def test_the_driver_actually_loses(path_drive) -> None:
    assert path_drive.lost
    assert path_drive.hp <= 0
    assert path_drive.state == "over"


def test_every_heart_is_taken(path_drive) -> None:
    assert len(path_drive.hits) >= 3


def test_it_has_to_leave_the_first_room_to_do_it(path_drive) -> None:
    # The room the hero wakes in has nobody in it at all, which is why a
    # hands-off go stands there unharmed for as long as you leave it.
    assert path_drive.room >= 1


def test_walking_straight_at_the_target_is_still_stuck() -> None:
    # The behaviour that spent a whole cycle in the first room. It is the
    # control: without it, "the path works" has nothing to be better than.
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    naive = drive(mode="naive")
    assert not naive.lost
    assert naive.room == 0


def test_cutting_a_way_through_is_worse_than_going_around() -> None:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    cutting = drive(mode="path", cut_grass=True)
    assert not cutting.lost
    assert cutting.room == 0
