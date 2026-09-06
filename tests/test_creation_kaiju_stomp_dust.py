"""The monster's footfall raises dust (§6 観察 2, C-1362).

Weight is stride and dust. The soldier's stride put dust down on every
footfall while the monster split the ground with a sound and nothing in
the air; the slam now raises a plume at the crack and kicks the camera
once, and the plume clears instead of fogging the arena.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import stomp_probe


@pytest.fixture(scope="module")
def slammed() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=stomp_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_slam_raises_a_plume_where_the_foot_came_down(slammed: dict) -> None:
    assert slammed["slam"] is not None, "the fight never slams"
    assert slammed["near"] >= 4, "the footfall raises no dust"


def test_the_slam_kicks_the_camera_once(slammed: dict) -> None:
    assert slammed["shakesAt"] == 1


def test_the_plume_clears(slammed: dict) -> None:
    assert slammed["cleared"] is not None, "the arena fogs over"
