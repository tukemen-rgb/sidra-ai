"""The giant moves like a giant (§6 観察 2, C-1684).

The observation is one sentence with two halves: 「多脚戦車は脚の周期が
遅く、接地のたびに土煙」. C-1362 built and measured the dust. The stride
had no instrument at all, so ``t/90`` and ``26`` inside ``legX()`` were
two constants nobody was holding - and ``creation_kaiju_stomp_dust``
stays green however fast the leg scurries, because that dust belongs to
the hero's footfalls and not the monster's.

Read as a comparison, because that is what the observation is about: the
giant reads huge next to something small that moves faster. The hero's
pace is walked, not taken from a constant, so the ratio is between two
things the page actually did.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import stride_probe

SLOWER_THAN_WALK = 5.0
FULL_CYCLE = 300  # frames
TRAVEL = 40.0  # px


@pytest.fixture(scope="module")
def stride() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to walk the fight")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=stride_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert got.returncode == 0, got.stderr[:400]
    seen = json.loads(got.stdout.strip().splitlines()[-1])
    leg, hero = seen["leg"], seen["me"]
    seen["legSteps"] = [abs(b - a) for a, b in zip(leg, leg[1:])]
    seen["heroSteps"] = [abs(b - a) for a, b in zip(hero, hero[1:])]
    signs = [1 if b > a else (-1 if b < a else 0) for a, b in zip(leg, leg[1:])]
    turns = [i for i, (a, b) in enumerate(zip(signs, signs[1:])) if a and b and a != b]
    seen["half"] = (
        min(b - a for a, b in zip(turns, turns[1:])) if len(turns) > 1 else len(leg)
    )
    seen["travel"] = max(leg) - min(leg)
    return seen


def test_the_fight_is_what_was_sampled(stride: dict) -> None:
    assert stride["state"] == "fight", stride["state"]
    assert max(stride["heroSteps"]) > 0, "the hero never walked"


def test_the_leg_is_far_slower_than_the_hero(stride: dict) -> None:
    """The comparison the observation is made of."""

    fast = max(stride["legSteps"])
    walk = max(stride["heroSteps"])
    assert fast > 0, "the leg never moved"
    assert walk / fast >= SLOWER_THAN_WALK, f"{walk / fast:.1f}x"


def test_a_stride_takes_seconds_not_frames(stride: dict) -> None:
    assert stride["half"] * 2 >= FULL_CYCLE, stride["half"] * 2


def test_slow_is_not_satisfied_by_still(stride: dict) -> None:
    """A leg pinned in place would pass every 'slow enough' test there is
    and would stop being a stride."""

    assert stride["travel"] >= TRAVEL, stride["travel"]


def test_the_walk_the_probe_compares_is_the_walk_the_page_uses(
    stride: dict,
) -> None:
    """The hero's pace was an argument written at a call site. Named once,
    it is the same number the page steers with and the probe reports -
    the shared-constant rule C-1342 set for the beats."""

    from sidra_ai.creation import kaiju

    assert "const LEG_PERIOD=90,LEG_SWING=26,ME_WALK=2.1;" in kaiju.KAIJU_SCRIPT
    assert "partsSteerX(me,ME_WALK," in kaiju.KAIJU_SCRIPT
    assert "partsSteerX(me,2.1," not in kaiju.KAIJU_SCRIPT
    assert stride["facts"]["walk"] == 2.1
    assert max(stride["heroSteps"]) == pytest.approx(stride["facts"]["walk"], abs=0.01)
