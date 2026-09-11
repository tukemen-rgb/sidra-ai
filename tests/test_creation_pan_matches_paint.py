"""The ear and the eye point at the same place (§28, C-1650).

GAG's intermediate hearing guideline asks that supplementary information
carried by audio - its own example is the direction you are being shot
from - be replicated in text or visuals. C-1394 gave SIDRA a pan channel
across ten sites, which is exactly that kind of information, and nothing
checked that the light lands where the pan says the event happened.

racing's slipstream was the case that failed. The sound was panned at the
obstacle and the burst was drawn over the car, and the reward only fires
when the two are 26..46px apart, so they could never agree by accident:
measured, the ear said 482px while the eye painted 448px.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.racing import ear_eye_probe


@pytest.fixture(scope="module")
def shaved() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("レースゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=ear_eye_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_slipstream_actually_pays_out(shaved) -> None:
    """A reward that never fired is not a pass, it is a reward that was
    never measured (C-1637)."""

    slip = shaved["slip"]

    assert slip is not None, "the staged near miss never paid"
    assert slip["heard"], "the slipstream made no sound"
    assert slip["seen"], "the slipstream showed no light"


def test_the_light_lands_where_the_pan_says(shaved) -> None:
    slip = shaved["slip"]
    width = shaved["width"]
    ear_x = slip["heard"][0]["at"] * width
    eye_x = min((s["x"] for s in slip["seen"]), key=lambda x: abs(x - ear_x))

    assert abs(eye_x - ear_x) <= 8, (ear_x, eye_x)


def test_the_two_channels_speak_in_the_same_frame(shaved) -> None:
    """A light a second later is not a replication of the sound."""

    slip = shaved["slip"]
    ear_frame = slip["heard"][0]["frame"]
    frames = [s["frame"] for s in slip["seen"]]

    assert any(abs(f - ear_frame) <= 1 for f in frames), (ear_frame, frames)


def test_the_near_miss_really_was_off_to_one_side(shaved) -> None:
    """The whole reason this matters: the event never happens at the car,
    so a light drawn on the car can never carry the side."""

    slip = shaved["slip"]

    assert abs(slip["obsX"] - slip["carX"]) >= 26, slip
