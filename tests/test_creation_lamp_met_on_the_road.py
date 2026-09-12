"""The lantern is met where it can be paid (§5, C-1714).

§5's word is 釣り合い. The adventure's half has been read by playing
since C-1702 - the village cut bare for the tap, each outlet priced by
actually paying it. The platformer's half was a SUM: ``ECON_PROBE``
counts the orbs the seed placed, compares the total with ``LAMP_COST``,
and never runs a frame.

Walked, the two facts came apart. On easy and normal the low road
reached the lantern holding **four** gems against a price of five, so
the auto-runner walked past its own insurance and finished at the flag
with six gems and an unlit lamp - the last two lying *after* the outlet.
A sum can be right while the order is wrong, and money collected past an
outlet is not that outlet's money.

Three separate rules used to decide how many gems lay behind the
lantern - every other platform carries one, the middle platform carries
the lantern, the lantern's own platform loses its gem - and none of them
had ever been compared with the price. The placement now takes the price
as an input: start at the middle and walk right to the first platform
with the price already behind it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import tapsink_probe

CEILING = 3.0
ROADS = (
    ("ジャンプで進むゲームを作って", "normal", True),
    ("ジャンプで進むゲームを作って やさしくして", "easy", True),
    # The harder course outruns the one-rule pilot, so geometry only -
    # the same treatment creation_soft_route gives it.
    ("ジャンプで進むゲームを作って 難しくして", "hard", False),
)


@pytest.fixture(scope="module")
def roads() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to walk the course")
    seen = {}
    for request, label, driven in ROADS:
        found = re.search(
            r"<script>(.*?)</script>", generate_game(request).html, re.S
        )
        assert found is not None, label
        got = subprocess.run(
            ["node", "-"],
            input=tapsink_probe(found.group(1)),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert got.returncode == 0, (label, got.stderr[:400])
        seen[label] = json.loads(got.stdout.strip().splitlines()[-1])
        seen[label]["driven"] = driven
    return seen


@pytest.mark.parametrize("label", [r[1] for r in ROADS])
def test_the_low_road_carries_the_price(roads: dict, label: str) -> None:
    """The claim that was already made - made here by walking."""

    road = roads[label]
    assert road["placed"]["low"] >= road["cost"], road["placed"]


@pytest.mark.parametrize("label", [r[1] for r in ROADS])
def test_the_price_is_asked_where_it_can_be_paid(roads: dict, label: str) -> None:
    """The order. This is the half a sum cannot see."""

    road = roads[label]
    assert road["placed"]["beforeLamp"] >= road["cost"], road["placed"]


@pytest.mark.parametrize("label", [r[1] for r in ROADS])
def test_the_gems_are_still_a_choice(roads: dict, label: str) -> None:
    """§5's ceiling, the same one the village is held to: past it the
    outlet stops being a decision and the gems are a number again."""

    road = roads[label]
    total = road["placed"]["low"] + road["placed"]["shelf"]
    assert total <= road["cost"] * CEILING, (total, road["cost"])


@pytest.mark.parametrize("label", [r[1] for r in ROADS if r[2]])
def test_the_pilot_lights_it_on_the_way_past(roads: dict, label: str) -> None:
    """And the road confirms the geometry rather than only agreeing with
    it: the page's own one-rule pilot arrives able to pay."""

    road = roads[label]
    assert road["goal"], road
    assert road["lit"], (road["heldNearLamp"], road["cost"])
    assert road["heldAtLamp"] >= road["cost"], road["heldAtLamp"]


def test_the_price_decides_where_the_lantern_stands() -> None:
    """Three rules used to decide how many gems lay behind it and none of
    them knew the price. The placement now reads it."""

    from sidra_ai.creation import platformer

    body = platformer.PLATFORMER_SCRIPT
    assert "o.x<cx-1).length>=LAMP_COST" in body
    assert "const mid=plats[Math.floor((plats.length-1)/2)];" not in body
