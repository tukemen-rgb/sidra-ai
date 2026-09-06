"""The monster wakes before it fights (§6 観察 3, C-1357).

The film's escalation opens every encounter - cracks run, a dust wall
rises, one wide shot shows the whole creature, a beat, then the fight -
and kaiju used to start mid-fight with none of it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import wake_probe


@pytest.fixture(scope="module")
def woken() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=wake_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_ground_cracks_then_the_dust_wall_rises(woken: dict) -> None:
    assert woken["early"]["state"] == "wake"
    assert woken["early"]["cracks"] > 0, "no cracks run when the ground stirs"
    assert woken["mid"]["dust"] > 0, "no dust wall rises"


def test_the_one_wide_shot_shows_the_whole_creature(woken: dict) -> None:
    assert woken["wideAt"]["wide"] is True


def test_the_soldier_watches_and_the_fight_takes_over(woken: dict) -> None:
    """A shot during the prologue lands nowhere; the handover is a fight."""

    assert woken["firedInWake"] == 0
    assert woken["toFight"] is not None and woken["toFight"] <= 120
    assert woken["after"]["state"] == "fight"
    assert woken["after"]["phase"] == "leg"
    assert woken["after"]["shots"] > 0, "the cannon stays dead after the handover"
