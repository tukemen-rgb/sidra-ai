"""The hero has a face (§1, C-1348).

The juice list ends with eyes and expressions, and every character was a
blank rectangle. The platformer hero looks where the run goes, lifts its
gaze on the rise, and blinks for one beat - and under reduced motion the
face never animates, because FRAME pins the eyes open.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import adv_face_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import face_probe


def _watched(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ジャンプで進むゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=face_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_eyes_follow_the_run_and_blink_briefly() -> None:
    seen = _watched()

    assert seen["lookRight"] == 1 and seen["lookLeft"] == -1, (
        "the eyes never follow the run"
    )
    assert seen["upWhileRising"], "the rise never lifts the gaze"
    assert seen["blinkFrames"] > 0, "the hero never blinks"
    assert seen["longestBlink"] <= 12, "the eyes stay shut"


def test_reduced_motion_keeps_the_eyes_open() -> None:
    seen = _watched(reduced=True)

    assert seen["lookRight"] == 1 and seen["lookLeft"] == -1
    assert seen["blinkFrames"] == 0, "reduced motion still blinks"


def _walked(*, reduced: bool = False) -> dict:
    """The adventure hero (C-1351), walked each of its four ways."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("迷宮を冒険するゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=adv_face_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_adventure_face_turns_with_the_walk_and_blinks() -> None:
    seen = _walked()

    assert seen["right"]["dir"] == 1 and seen["right"]["shown"]
    assert seen["left"]["dir"] == 3 and seen["left"]["shown"]
    assert seen["down"]["dir"] == 2 and seen["down"]["shown"]
    assert seen["blinkFrames"] > 0, "the hero never blinks"
    assert seen["longestBlink"] <= 12, "the eyes stay shut"


def test_the_back_of_the_head_has_no_eyes() -> None:
    """Facing up is the back of the head: nothing to draw, honestly."""

    seen = _walked()

    assert seen["up"]["dir"] == 0
    assert seen["up"]["shown"] is False


def test_reduced_motion_keeps_the_adventure_eyes_open() -> None:
    seen = _walked(reduced=True)

    assert seen["right"]["dir"] == 1
    assert seen["blinkFrames"] == 0, "reduced motion still blinks"
