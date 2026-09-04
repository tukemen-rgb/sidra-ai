"""The puzzle round's sky, judged by playing the round out (§7, C-1327).

The last of the ten templates to get its skies: the puzzle has no course
and no falling world, so its journey is §8's sixty seconds, the same clock
the fishing and catch rounds spend. The probe passes the briefing, pops a
group under the first sky, ages the page into each later third, pops
another under the last sky, and confirms the clock still calls the break -
two pops leave the board far from a deadlock, so 'time' is the only honest
ending.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.puzzle import sky_probe


def _played(request: str = "パズルゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=sky_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_sky_steps_with_played_time():
    played = _played()

    assert played["sceneEarly"] == 0
    assert played["sceneMid"] == 1
    assert played["sceneLate"] == 2
    assert played["msMid"] >= 20000, "the second sky waits for the second third"
    assert played["msLate"] >= 40000, "the last sky waits for the last third"


def test_the_last_stretch_is_the_brightest_sky_of_the_round():
    played = _played()
    scenes = played["scenes"]

    assert len(scenes) == 3
    assert len({s["floor"] for s in scenes}) == 3, "each third paints its own sky"
    assert scenes[2]["lum"] > scenes[0]["lum"]
    assert scenes[2]["lum"] >= scenes[1]["lum"]


def test_a_pop_lands_under_the_first_and_the_final_sky():
    """The arc decorates the round; the puzzle underneath is intact."""

    played = _played()

    assert played["popEarly"] == 1, "a walked-to pop scores in act 0"
    assert played["popLate"] == 1, "a walked-to pop scores in act 2"
    assert played["score"] >= 8, "two groups of two or more were paid"


def test_the_round_still_breaks_at_sixty_seconds():
    played = _played()

    assert played["state"] == "play", "two pops must not deadlock the board"
    assert played["done"] is True
    assert played["reason"] == "time", "the clock, not the sky, ends the go"
