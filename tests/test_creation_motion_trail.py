"""A moving body leaves motion in the air (§1, C-1366 / C-1372 / C-1628).

The technique list's three particle kinds are smoke, destruction and
trails - and trails existed nowhere. Three bodies have one now: the
marble, the racing car, and the platformer's hero, whose whole verb is
moving. All three keep the same shape - ten fading afterimages, filling
while the body moves, every sample behind it, draining once it stops,
never accumulating under reduced motion.

The platformer needs one reading the others do not. Its run is a single
speed (``me.x`` moves by ``RUN`` or not at all), so "speed draws the
length" cannot be shown sideways; the one place this template's speed
varies is the fall, which accelerates under gravity. The streak has to
stretch there, and the probe measures the height it spans while running
flat against the height it spans while falling.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.marble import trail_probe
from sidra_ai.creation.platformer import trail_probe as plat_trail_probe
from sidra_ai.creation.racing import trail_probe as racing_trail_probe


def _rolled(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("玉転がしゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=trail_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_rolling_marble_streaks_behind_itself() -> None:
    seen = _rolled()

    assert seen["full"] == 10, "the streak never fills"
    assert seen["behind"], "an afterimage sits ahead of the marble"
    assert seen["drained"] is not None, "the stopped marble keeps its streak"


def test_reduced_motion_never_accumulates_one() -> None:
    seen = _rolled(reduced=True)

    assert seen["full"] == 0, "reduced motion still streaks"


def _raced(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("レースゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=racing_trail_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_racing_car_streaks_and_speed_draws_the_length() -> None:
    seen = _raced()

    assert seen["full"] == 10, "the streak never fills"
    assert seen["behind"], "an afterimage sits ahead of the car"
    assert seen["slowSpan"] < seen["fastSpan"] * 0.7, "speed does not draw the length"
    assert seen["drained"] is not None, "the finished run keeps its streak"


def test_racing_reduced_motion_never_accumulates_one() -> None:
    seen = _raced(reduced=True)

    assert seen["full"] == 0, "reduced motion still streaks"


def _ran(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ジャンプで進むゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=plat_trail_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_running_hero_streaks_behind_itself() -> None:
    seen = _ran()

    assert seen["full"] == 10, "the streak never fills"
    assert seen["behind"], "an afterimage sits ahead of the hero"
    assert seen["runSpan"] > 10, f"the streak is {seen['runSpan']} long"


def test_the_standing_hero_has_no_tail() -> None:
    """Which is the whole reason the length means speed."""

    seen = _ran()

    assert seen["still"], "the hero never landed, so this proves nothing"
    assert seen["drained"] is not None, "the standing hero keeps its streak"
    assert seen["stillTrail"] == 0
    assert seen["stillPainted"] == 0, "an afterimage is still on screen"


def test_the_afterimages_are_painted_and_not_merely_counted() -> None:
    """The trap C-1615 and C-1618 each fell into once: a probe that reads a
    facts function proves the number, not that it reaches the canvas."""

    seen = _ran()

    assert seen["painted"] == 10, f"{seen['painted']} afterimages were drawn"
    assert 0 < seen["paintedMax"] < 1, seen["paintedMax"]


def test_the_fall_stretches_the_streak() -> None:
    """The one place this template's speed varies is gravity."""

    seen = _ran()

    assert seen["fallFull"] == 10
    assert seen["fallSpanY"] > seen["walkSpanY"] + 1, (
        seen["fallSpanY"], seen["walkSpanY"]
    )


def test_platformer_reduced_motion_never_accumulates_one() -> None:
    seen = _ran(reduced=True)

    assert seen["full"] == 0, "reduced motion still streaks"
    assert seen["fallFull"] == 0, "a reduced-motion fall still streaks"
    assert seen["painted"] == 0, "reduced motion still paints afterimages"


# ---------------------------------------------- the canvas, not the books


def test_the_marble_paints_the_afterimages_it_counts() -> None:
    """C-1632: this body's probe read ``marbleFacts().trail`` and nothing
    else, so removing the draw entirely would have left it at full marks.

    Eight of the ten, and that is the page being right: the two oldest sit
    more than 34 units back, past the corridor's near plane, and the page's
    own ``d<NEAR`` guard drops them. They are the faintest two.
    """

    seen = _rolled()

    assert seen["bodyDrawn"], "the marble itself was not drawn in this frame"
    assert seen["painted"] == 8, seen["painted"]
    assert 0 < seen["paintedMax"] <= 0.2201


def test_the_car_paints_the_afterimages_it_counts() -> None:
    seen = _raced()

    assert seen["bodyDrawn"], "the car itself was not drawn in this frame"
    assert seen["painted"] == 10, seen["painted"]
    assert 0 < seen["paintedMax"] <= 0.2801


@pytest.mark.parametrize("drive", ["marble", "racing"])
def test_reduced_motion_paints_no_afterimage_either(drive: str) -> None:
    """Counting none and drawing none are two claims; the second one is
    what a player would see."""

    seen = _rolled(reduced=True) if drive == "marble" else _raced(reduced=True)

    assert seen["painted"] == 0
    assert seen["bodyDrawn"], "nothing was drawn at all, so this proves nothing"
