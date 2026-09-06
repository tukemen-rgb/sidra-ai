"""The bars step back for the heavy beats (§2×§21, C-1371).

The reference mix ducks everything but the moment's most important sound
to -9dB and releases over a second. SIDRA's dialogue-equivalents are the
win phrase, the lose noise and the milestone powerup - and only those:
a duck on every pickup would be the overuse the reference warns about.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.music import duck_probe


@pytest.fixture(scope="module")
def heard() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ゲームを作って", template="catch").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=duck_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_win_pulls_the_bars_to_minus_nine(heard: dict) -> None:
    assert heard["calm"] and min(heard["calm"]) >= 0.04, "the calm bars are not at height"
    assert heard["ducked"], "no note was heard under the fanfare"
    for v in heard["ducked"]:
        base = 0.045 if v < 0.017 else 0.055
        assert 0.3 <= v / base <= 0.4, f"a note under the fanfare sits at {v}"


def test_the_bars_come_all_the_way_back(heard: dict) -> None:
    assert len(heard["recovered"]) >= 3
    assert min(heard["recovered"]) >= 0.0449, "the bars never come back"


def test_only_the_heavy_voices_duck(heard: dict) -> None:
    assert heard["duckAfterGem"] == 1, "a light pickup ducks the music"
    assert heard["duckAfterLose"] == 0.35
    assert heard["duckAfterPowerup"] == 0.35
