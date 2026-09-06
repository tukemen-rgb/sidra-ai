"""The pass is heard where it happens (§2, C-1364).

sfxr lists low-pass AND high-pass. C-1308 built the falling low-pass
thud; the rising high-pass - thin air past the ear - was never built,
and the graze sparked in silence. Every counted graze now whooshes,
once per hazard, silent under M, while the hurt keeps its thud.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.graze import whoosh_probe


@pytest.fixture(scope="module")
def heard() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("シューティングゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=whoosh_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_each_graze_is_air_through_a_rising_highpass(heard: dict) -> None:
    for label in ("first", "second"):
        seen = heard[label]
        assert seen["nodes"] == ["noise->highpass", "highpass->out"], label
        assert seen["freqs"][0] < seen["freqs"][-1], f"{label}: the whoosh falls"


def test_the_same_hazard_never_whooshes_twice(heard: dict) -> None:
    assert heard["repeatNodes"] == 0


def test_the_mute_wins_and_the_hurt_keeps_its_thud(heard: dict) -> None:
    assert heard["mutedNodes"] == 0, "muted, and the air played anyway"
    assert heard["hurtNodes"] == ["noise->lowpass", "lowpass->out"]
