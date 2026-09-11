"""The hold has a ladder too (§1, C-1687).

§1's technique list names hitstop and knockback as one pair, and
Vlambeer's rule is that the beat is proportional to the event's weight.
``creation_shake_ladder`` pins that for the camera across six templates,
and says in its own detail that it does not read source literals -
「それは帳簿で、C-1640 で潰した形」. The other half of the pair had no
ladder at all: every ``hitstop()`` in the tree could be levelled to one
number and the board would stay green.

Read where the page asks for the hold. ``HITSTOP`` is a small integer
that decays a frame at a time, so a reading taken after the frame has run
cannot tell a three-frame hold from a one-frame one; the number asked for
is computed at run time (puzzle's is ``cells.length>4?3:1``), so it is
still the canvas and not the ledger.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import run_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import beats_probe


def _drive(request: str, probe) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to land the blows")
    page = generate_game(request).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def dungeon() -> dict:
    return _drive("迷宮を冒険するゲームを作って", run_probe)["walked"]


@pytest.fixture(scope="module")
def monster() -> dict:
    return _drive("巨大怪獣と戦うゲームを作って", beats_probe)


def test_the_dungeons_three_rungs_climb(dungeon: dict) -> None:
    assert dungeon["state"] == "win", "the run did not reach the fall"
    roamer, guard, fall = (
        dungeon["holdRoamer"],
        dungeon["holdGuard"],
        dungeon["holdFall"],
    )
    assert roamer < guard < fall, (roamer, guard, fall)


def test_the_lightest_blow_still_stops(dungeon: dict) -> None:
    """"Heavier is longer" is satisfied by every rung being zero. A game
    that stopped for nothing would pass a ladder test and have no hitstop
    at all."""

    assert dungeon["holdRoamer"] >= 1, dungeon["holdRoamer"]


def test_the_monsters_head_holds_longer_than_its_leg(monster: dict) -> None:
    assert monster["head"]["landed"], "the head was never struck"
    assert monster["buckleHold"] >= 1, "the leg buckling stops nothing"
    assert monster["buckleHold"] < monster["head"]["hold"], (
        monster["buckleHold"],
        monster["head"]["hold"],
    )


def test_the_first_leg_hit_asks_for_no_hold(monster: dict) -> None:
    """Not a defect, and worth pinning so a later reading is not taken
    from the wrong beat: ``hitLeg()`` shakes on every hit and asks for a
    hold only when the leg gives."""

    assert monster["leg"]["landed"]
    assert monster["leg"]["hold"] == 0, monster["leg"]["hold"]


def test_the_hold_can_be_read_at_all(monster: dict) -> None:
    """``hitstopFrames()`` is the reader ``shakeAmount()`` always had. A
    channel with no reader is a channel measured off literals."""

    from sidra_ai.creation import juice

    assert "function hitstopFrames(){return HITSTOP}" in juice.JUICE_PREAMBLE
    assert "hitstopFrames" in juice.PREAMBLE_NAMES
