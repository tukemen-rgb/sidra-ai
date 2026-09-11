"""A sink returns value, or it does not take the payment (§5, C-1673).

§5's fact is an economy one: collectibles need an outlet, and taps and
sinks have to balance. C-1021 built the outlets - the shrine trades three
gems for a heart, the optional door costs two - and C-1376 proved a
player can always afford them. Nothing asked what the payment buys.

Measured before fixed: ``hero.maxhp=Math.min(5,hero.maxhp+1)`` saturated
in silence, so at five hearts the shrine still took three gems, still
said ``ハートが増えた``, still rang powerUp and still threw eighteen
particles. Nine of the village's fifteen gems could be destroyed by a
celebration indistinguishable from a real purchase - and the optional
door costs two, so the lie could price a player out of §3's branch.

The contract runs in both directions: what a purchase must deliver, and
what the shrine must refuse to take. The platformer's lantern is here
because it already got this right (``!lamp.lit``) with nothing holding it
there.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import sink_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import lamp_sink_probe

DOOR_COST = 2  # §3's optional door, in gems


def _script(page: str) -> str:
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None, "the page carries no script"
    return found.group(1)


def _drive(probe: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    got = subprocess.run(
        ["node", "-"], input=probe, capture_output=True, text=True, timeout=180
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def shrine() -> dict:
    page = generate_game("迷宮を冒険するゲームを作って").html
    return _drive(sink_probe(_script(page)))


@pytest.fixture(scope="module")
def lantern() -> dict:
    page = generate_game("ゲームを作って", template="platformer").html
    return _drive(lamp_sink_probe(_script(page)))


def _paid(shrine: dict) -> list[dict]:
    return [b for b in shrine["buys"] if b["gemsAfter"] < b["gemsBefore"]]


def _refused(shrine: dict) -> list[dict]:
    return [b for b in shrine["buys"] if b["gemsAfter"] == b["gemsBefore"]]


def test_the_village_can_fill_the_purse(shrine: dict) -> None:
    """The run is the ceiling run: every tuft cut, every tuft paying."""

    assert shrine["shrine"], "no shrine stands on the map"
    assert shrine["cuts"] > 0, "the blade cut nothing"
    assert shrine["purse"] == shrine["cuts"], (
        f"{shrine['cuts']} tufts paid {shrine['purse']} gems"
    )


def test_each_accepted_payment_buys_exactly_one_heart(shrine: dict) -> None:
    paid = _paid(shrine)
    assert paid, "the shrine never took a gem"
    for buy in paid:
        assert buy["gemsBefore"] - buy["gemsAfter"] == 3, buy
        assert buy["heartsAfter"] == buy["heartsBefore"] + 1, buy


def test_a_purchase_is_celebrated(shrine: dict) -> None:
    """The half that already worked, pinned: a real sale rings and bursts."""

    for buy in _paid(shrine):
        assert "powerup" in buy["heard"], buy
        assert buy["thrown"] > 0, buy
        assert buy["said"], buy


def test_the_ceiling_refuses_the_payment(shrine: dict) -> None:
    """The defect itself: at the ceiling the gems must stay in the purse."""

    refused = _refused(shrine)
    assert refused, "every touch was taken; nothing refuses payment"
    for touch in refused:
        assert touch["gemsAfter"] == touch["gemsBefore"], touch
        assert touch["heartsAfter"] == touch["heartsBefore"], touch


def test_the_refusal_does_not_sound_like_a_sale(shrine: dict) -> None:
    """Taking nothing while celebrating is a quieter version of the same
    fault: the player learns the wrong thing about their own purse."""

    sold = {buy["said"] for buy in _paid(shrine)}
    for touch in _refused(shrine):
        assert touch["said"], "the refusal says nothing at all"
        assert touch["said"] not in sold, touch["said"]
        assert "powerup" not in touch["heard"], touch
        assert touch["thrown"] == 0, touch


def test_the_purse_survives_the_ceiling_for_the_door(shrine: dict) -> None:
    """§3's branch is bought with the same gems. A shrine that swallowed
    them at the ceiling could price a player out of the charm behind the
    optional door - which is what makes this an economy fault and not a
    cosmetic one."""

    left = shrine["buys"][-1]["gemsAfter"]
    assert left >= DOOR_COST, (
        f"{left} gems left after filling the hearts; the door costs {DOOR_COST}"
    )


def test_the_lantern_lights_once_for_its_price(lantern: dict) -> None:
    first = lantern["first"]
    assert first["litAfter"], "the lantern did not light"
    assert first["gemsBefore"] - first["gemsAfter"] == lantern["cost"], first
    assert "powerup" in first["heard"], first


def test_the_lit_lantern_takes_nothing_more(lantern: dict) -> None:
    """The template that got it right, held there."""

    again = lantern["again"]
    assert again["litBefore"] and again["litAfter"], again
    assert again["gemsAfter"] == again["gemsBefore"], again
    assert "powerup" not in again["heard"], again
    assert again["said"] != lantern["first"]["said"], again
