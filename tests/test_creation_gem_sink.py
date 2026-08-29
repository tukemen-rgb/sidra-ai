"""Gems that buy something, and a door the run does not need.

Both failures here are invisible from outside: a collectible with no outlet
still counts up, and a dungeon with one path still finishes. The world is
built by running the page rather than by reading it, because "the tile is
defined" and "the tile is on the map" have been different facts before.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import world_probe
from sidra_ai.creation.games import generate_game, validate_game_html

SHRINE, DOOR, CHARM, WALL = 9, 10, 11, 1


def _world(request: str = "冒険ゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is needed to build the world")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    finished = subprocess.run(
        ["node", "-"],
        input=world_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert finished.returncode == 0, finished.stderr[:400]
    return json.loads(finished.stdout)


def test_the_shrine_the_door_and_the_reward_are_all_really_placed():
    tiles = _world()["tiles"]

    for code in (SHRINE, DOOR, CHARM):
        assert tiles.get(str(code)), f"tile {code} is defined but not on the map"


def test_the_reward_is_reachable_only_through_the_optional_door():
    # A second opening turns the branch back into a straight line with an
    # ornament on it, which is the thing §3 says is not worth building.
    neighbours = _world()["charmNeighbours"]

    assert neighbours.count(DOOR) == 1
    assert all(n == WALL for n in neighbours if n != DOOR)


def test_gems_are_spent_in_two_places():
    page = generate_game("冒険ゲームを作って").html

    assert page.count("hero.gems-=") >= 2


def test_the_run_starts_with_nothing_bought():
    # The reward and the extra heart have to be earned inside the run; a
    # world that handed them over at reset would pass every other check.
    world = _world()

    assert world["gems"] == 0
    assert world["charm"] is False
    assert world["hearts"] == 3


def test_the_page_still_runs_with_the_branch_in_it():
    verdict = validate_game_html(generate_game("冒険ゲームを作って").html)

    assert verdict["playable"], verdict["failures"]


def test_the_shrine_and_the_door_block_movement():
    # Walking through the door would make the price optional in the wrong
    # sense - the reward would be free.
    page = generate_game("冒険ゲームを作って").html

    assert "t===9||t===10" in page


def test_the_new_tiles_carry_a_shape_and_not_only_a_colour():
    # C-1018's rule: essential information never by fixed colour alone.
    page = generate_game("冒険ゲームを作って").html

    assert "function diamond(" in page
