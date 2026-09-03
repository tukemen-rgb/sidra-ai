"""The marble's corridor, judged by rolling it (§7 at course scale, C-1307).

The probe pilots the run - into gates, away from blocks - and reads the
act of the sky off the running page as each third of the course passes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.marble import probe_source


def _rolled(request: str = "玉転がしゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_course_is_three_acts_and_the_sky_steps_with_the_distance():
    rolled = _rolled()

    assert rolled["sceneEarly"] == 0
    assert rolled["sceneMid"] == 1
    assert rolled["sceneLate"] == 2
    assert rolled["z"] >= rolled["course"] * 2 / 3, "the pilot reached the final act"


def test_the_final_stretch_is_the_brightest_sky_of_the_run():
    rolled = _rolled()
    scenes = rolled["scenes"]

    assert len(scenes) == 3
    assert len({s["floor"] for s in scenes}) == 3, "each act paints its own sky"
    assert scenes[2]["lum"] > scenes[0]["lum"]
    assert scenes[2]["lum"] >= scenes[1]["lum"]


def test_the_pilot_actually_plays_the_course():
    """Gates rolled through, not merely frames survived: the probe steers."""

    rolled = _rolled()

    assert rolled["state"] == "over"
    assert rolled["gates"] >= 10
