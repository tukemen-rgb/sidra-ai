"""The kick settles, and it is still a kick (§1, C-1701).

Vlambeer's sentence, quoted in §1, carries three instructions: kick the
camera a few px on a heavy hit, **decay it fast**, and scale it with the
weight of the event. ``creation_shake_ladder`` holds the third across six
templates - and says in its own comment that "the decay half was wired
from the start". Wired, not held.

Change ``SHAKE*=0.78`` to ``0.995`` and the ladder keeps its order while
the screen wobbles for two seconds after every hit. Change it to ``0.01``
and the kick is a one-frame flicker nobody reads as weight. Both are
failures of the same instruction, in opposite directions.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.juice import settle_probe

HALF = 6  # frames
ALIVE = 1.0  # px, three frames in
ZERO = 30  # frames to rest


@pytest.fixture(scope="module")
def trail() -> list[float]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to kick the camera")
    html = generate_game("迷宮を冒険するゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=settle_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])["trail"]


def test_the_kick_lands(trail: list[float]) -> None:
    assert trail[0] > 0, trail[:4]


def test_it_halves_fast(trail: list[float]) -> None:
    peak = trail[0]
    half = next((i for i, v in enumerate(trail) if v <= peak / 2), None)
    assert half is not None and half <= HALF, (half, trail[:12])


def test_fast_is_not_satisfied_by_gone(trail: list[float]) -> None:
    """The other direction. A kick that vanishes in a frame reads as a
    flicker, not as weight - and it would pass every "decays fast" test
    written without this line."""

    assert trail[3] >= ALIVE, (trail[3], trail[:6])


def test_the_camera_comes_to_rest(trail: list[float]) -> None:
    rest = next((i for i, v in enumerate(trail) if v == 0), None)
    assert rest is not None and rest <= ZERO, (rest, len(trail))


def test_the_curve_only_falls(trail: list[float]) -> None:
    """One kick, left alone: nothing should add to it on the way down."""

    for earlier, later in zip(trail, trail[1:]):
        assert later <= earlier + 1e-9, (earlier, later)
