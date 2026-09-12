"""One weight, read on three dials (§1, C-1716).

§1 lists 「被弾時のヒットストップとノックバック」 as one pair, and
Vlambeer's rule is that the beat is proportional to the event's weight -
*one* weight. The page answers with three independent numbers: the
camera's kick, the hold's frames, the shove's distance.

Two of the three had a ladder. ``creation_shake_ladder`` compares a light
and a heavy event across six templates; ``creation_hold_ladder`` does the
same for the hold across two. The shove had none - ``creation_hit_knockback``
asks whether it happens, points away from the attacker, obeys the walls
and decays to rest, and never whether it is proportional. Its own detail
reported +12px against +20px: the ladder was being measured and not held.

Nothing required the three to agree, either. Drop the guardian's shove to
the roamer's and every judge above stays green while 「重い一撃」 shakes
harder, stops longer, and pushes exactly as far as a light one.

Both blows are taken in one run on open floor found from the map: a shove
taken beside a wall is clamped by ``solid()``, and a clamped throw says
nothing about how hard it was thrown.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import weight_probe
from sidra_ai.creation.games import generate_game

REQUESTS = ("迷宮を冒険するゲームを作って", "難しい冒険ゲームを作って")


@pytest.fixture(scope="module")
def blows() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to take the blows")
    seen = {}
    for request in REQUESTS:
        found = re.search(r"<script>(.*?)</script>", generate_game(request).html, re.S)
        assert found is not None, request
        got = subprocess.run(
            ["node", "-"],
            input=weight_probe(found.group(1)),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert got.returncode == 0, (request, got.stderr[:400])
        seen[request] = json.loads(got.stdout.strip().splitlines()[-1])
    return seen


@pytest.mark.parametrize("request_text", REQUESTS)
def test_both_blows_actually_landed(blows: dict, request_text: str) -> None:
    hurt = blows[request_text]["hurt"]
    assert hurt["roam"] >= 1 and hurt["guard"] >= 1, hurt


@pytest.mark.parametrize("request_text", REQUESTS)
def test_the_heavier_blow_throws_further(blows: dict, request_text: str) -> None:
    seen = blows[request_text]
    assert seen["roam"]["shove"] > 0, "the light blow shoves nobody"
    assert seen["guard"]["shove"] > seen["roam"]["shove"], (
        seen["roam"]["shove"],
        seen["guard"]["shove"],
    )


@pytest.mark.parametrize("request_text", REQUESTS)
def test_the_distance_asked_for_is_the_distance_travelled(
    blows: dict, request_text: str
) -> None:
    """On open floor there is nothing to clamp it, so a ladder the page
    never acts on shows up here."""

    for who in ("roam", "guard"):
        seen = blows[request_text][who]
        assert seen["moved"] == pytest.approx(seen["shove"], abs=0.01), (who, seen)


@pytest.mark.parametrize("request_text", REQUESTS)
def test_the_three_dials_point_the_same_way(blows: dict, request_text: str) -> None:
    """The part that is really missing. The weight is one thing; three
    numbers that can disagree are three weights."""

    seen = blows[request_text]
    for dial in ("kick", "hold", "shove"):
        light, heavy = seen["roam"][dial], seen["guard"][dial]
        assert light is not None and heavy is not None, (dial, light, heavy)
        assert heavy > light, (dial, light, heavy)


def test_the_two_distances_are_named_once() -> None:
    """They were bare literals at their call sites - the writing side of
    the shape C-1640 closed on the reading side. The camera has
    shakeAmount() and the hold has hitstopFrames(); this is the third."""

    from sidra_ai.creation import adventure

    body = adventure.ADVENTURE_SCRIPT
    assert "const KNOCK_ROAM=12,KNOCK_GUARD=20;" in body
    assert "function shoveAmount(kind)" in body
    assert "/kd*12" not in body and "/gd*20" not in body
