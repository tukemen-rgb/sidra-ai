"""The shot leaves a trail (§1, C-1389).

§1's particle list names three siblings - smoke, debris, trails - and the
trail was the one nowhere in ten templates: every shot was a rectangle
existing for one frame at a time. Now one real shot paints a full-alpha
head with two fading afterimages one and two flight-steps behind on every
flight frame, and under reduced motion the same shot flies head-only.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.kaiju import trail_probe as kaiju_trail
from sidra_ai.creation.shooter import trail_probe as shooter_trail

_PROBES = {"shooter": shooter_trail, "kaiju": kaiju_trail}
_REQUESTS = {"shooter": "ゲームを作って", "kaiju": "巨大怪獣と戦うゲームを作って"}


def _drive(template: str, *, reduced: bool) -> dict:
    html = generate_game(_REQUESTS[template], template=template).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=_PROBES[template](script, reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", ["shooter", "kaiju"])
def test_every_flight_frame_paints_the_full_trail(template: str) -> None:
    got = _drive(template, reduced=False)
    assert got["fired"] == 1 and got["watched"] >= 10, "the shot never flew"
    assert got["headFrames"] == got["watched"], "the head flickers"
    assert got["fullTrail"] == got["watched"], "the trail breaks"


@pytest.mark.parametrize("template", ["shooter", "kaiju"])
def test_reduced_motion_flies_head_only(template: str) -> None:
    got = _drive(template, reduced=True)
    assert got["fired"] == 1 and got["watched"] >= 10, "the shot never flew"
    assert got["headFrames"] == got["watched"], "reduced motion loses the head"
    assert got["ghosts"] == 0, "reduced motion still streaks"
