"""C-1412: the corridor's past self, met at the same place on the course.

C-1401's trail, wired to its second template. z down the corridor is the
same shape as distance around a lap, so the trail, the key and the switch
carried over unchanged.

What these tests are for that the shared ghost tests are not: §11's rule
is that the trail is indexed by *progress*, not by the clock. Running a
template against itself at one speed cannot tell those apart - a
frame-keyed trail agrees with itself perfectly. So the second roll here is
a deliberately faster one, and the ghost it draws is compared against
where the first roll actually was at that point on the course.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.ghost import GHOST_STEP, GHOST_TEMPLATES, GHOST_UNWIRED
from sidra_ai.creation.marble import ghost_probe_source

BASE = {"sidra.seen.marble": "1"}
#: A bucket spans GHOST_STEP of course, which is a frame or two of rolling,
#: and the marble steers 3.4 a frame. Anything inside this is the sampling
#: grain; a trail keyed to the clock misses by lane-widths, not by pixels.
TOLERANCE = 24


def _roll(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to roll the page")
    page = generate_game("玉転がしを作って", template="marble").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=ghost_probe_source(script.group(1), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def runs() -> dict:
    first = _roll(stored=dict(BASE))
    assert first["trail"], "the first roll banked nothing to replay"
    carried = {**BASE, "sidra.ghost.marble": first["trail"]}
    return {
        "first": first,
        "fast": _roll(stored=dict(carried), roll=9.0),
        "off": _roll(
            stored={**carried, "sidra.tune.marble": {"ghost": False, "speed": 9.0}}
        ),
    }


def test_marble_is_wired_and_says_so():
    assert "marble" in GHOST_TEMPLATES
    assert "marble" not in GHOST_UNWIRED


def test_the_first_roll_has_no_ghost_and_leaves_one(runs):
    first = runs["first"]
    assert not first["ghost"]["had"]
    assert first["ghost"]["drawn"] == 0
    assert first["ghost"]["saved"] >= 1


def test_the_second_roll_is_actually_faster(runs):
    # Without this the comparison below proves nothing about indexing.
    assert runs["fast"]["spd"] > runs["first"]["spd"]
    assert runs["fast"]["frames"] < runs["first"]["frames"]


def test_the_ghost_is_where_the_first_roll_was_on_the_course(runs):
    first, fast = runs["first"], runs["fast"]
    assert fast["ghost"]["drawn"] > 0, "the faster roll met no ghost"
    checked = worst = 0
    for bucket, drew in fast["seen"]:
        target = bucket * GHOST_STEP
        near, gap = None, 1e9
        for was_z, was_x in first["path"]:
            distance = abs(was_z - target)
            if distance < gap:
                gap, near = distance, was_x
        if near is None or gap > GHOST_STEP:
            continue
        checked += 1
        worst = max(worst, abs(drew - near))
    assert checked >= 100, f"only {checked} points of the course could be compared"
    assert worst <= TOLERANCE, f"the ghost drifted {worst}px"


def test_the_switch_puts_the_ghost_away(runs):
    assert runs["off"]["ghost"]["drawn"] == 0
    assert runs["off"]["ghost"]["on"] is False


def test_the_ghost_touches_nothing(runs):
    # The same roll, with the memory and without it. A past run that moved
    # the present one would be a second marble rather than a memory.
    assert runs["off"]["path"] == runs["fast"]["path"]
    assert runs["off"]["ghost"]["runHash"] == runs["fast"]["ghost"]["runHash"]
