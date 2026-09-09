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
from sidra_ai.creation.catchgame import catch_face_probe
from sidra_ai.creation.duel import face_probe as duel_face_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import face_probe as kaiju_face_probe
from sidra_ai.creation.marble import face_probe as marble_face_probe
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


def _caught(*, reduced: bool = False) -> dict:
    """The catch basket (C-1353), parked and lined up under the falls."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("落ちものキャッチを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=catch_face_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_basket_watches_the_next_item_and_blinks() -> None:
    seen = _caught()

    assert seen["lookRight"] == 1, "an item to the right never pulls the eyes"
    assert seen["lookLeft"] == -1, "an item to the left never pulls the eyes"
    assert seen["lookCentred"] == 0, "an item overhead still pulls the eyes sideways"
    assert seen["blinkFrames"] > 0, "the basket never blinks"
    assert seen["longestBlink"] <= 12, "the eyes stay shut"


def test_reduced_motion_keeps_the_basket_eyes_open() -> None:
    seen = _caught(reduced=True)

    assert seen["lookRight"] == 1
    assert seen["blinkFrames"] == 0, "reduced motion still blinks"


def _duelled(*, reduced: bool = False) -> dict:
    """The duel fighter (C-1355), stared at from each lane relation."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ビームで撃ち合うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=duel_face_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_fighter_watches_the_enemy_lane_and_blinks() -> None:
    seen = _duelled()

    assert seen["below"] == 1, "an enemy below never pulls the eyes down"
    assert seen["above"] == -1, "an enemy above never pulls the eyes up"
    assert seen["level"] == 0, "a met stare still pulls the eyes aside"
    assert seen["blinkFrames"] > 0, "the fighter never blinks"
    assert seen["longestBlink"] <= 12, "the eyes stay shut"


def test_reduced_motion_keeps_the_fighter_eyes_open() -> None:
    seen = _duelled(reduced=True)

    assert seen["below"] == 1
    assert seen["blinkFrames"] == 0, "reduced motion still blinks"


def _piloted(*, reduced: bool = False) -> dict:
    """The kaiju pilot (C-1363), parked on each side of the monster's leg."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=kaiju_face_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_pilot_watches_the_monster_and_blinks() -> None:
    seen = _piloted()

    assert seen["legRight"] == 1, "a leg to the right never pulls the eyes"
    assert seen["legLeft"] == -1, "a leg to the left never pulls the eyes"
    assert seen["underLeg"] == 0, "standing under the leg still pulls the eyes aside"
    assert seen["blinkFrames"] > 0, "the pilot never blinks"
    assert seen["longestBlink"] <= 12, "the eyes stay shut"


def test_reduced_motion_keeps_the_pilot_eyes_open() -> None:
    seen = _piloted(reduced=True)

    assert seen["legRight"] == 1
    assert seen["blinkFrames"] == 0, "reduced motion still blinks"


def _rolled(*, reduced: bool = False) -> dict:
    """C-1618: the marble, the one avatar on screen at all times."""

    if shutil.which("node") is None:
        pytest.skip("node is required to drive the page")
    page = generate_game("玉転がしゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=marble_face_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_marble_watches_what_is_coming_and_blinks() -> None:
    seen = _rolled()

    assert seen["lookRight"] == 1, "a gate to the right never pulls the eyes"
    assert seen["lookLeft"] == -1, "a gate to the left never pulls the eyes"
    assert seen["lookCentred"] == 0, "a gate just off centre still pulls the eyes"
    # ...and the look reaches the paint, not just the contract (C-1615's
    # lesson): the pair is really drawn and really moves.
    assert seen["eyesDrawn"] >= 2, "the eyes never reach the paint"
    assert seen["eyeXRight"] > seen["eyeXLeft"], "the drawn eyes do not move"
    assert seen["blinkFrames"] > 0, "the marble never blinks"
    assert seen["longestBlink"] <= 12, "the eyes stay shut"


def test_reduced_motion_keeps_the_marble_eyes_open() -> None:
    seen = _rolled(reduced=True)

    assert seen["lookRight"] == 1, "the look is not decoration - it stays"
    assert seen["blinkFrames"] == 0, "reduced motion still blinks"
