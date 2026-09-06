"""The marble leaves motion in the air (§1, C-1366).

The technique list's three particle kinds are smoke, destruction and
trails - and trails existed nowhere. The marble now leaves ten fading
afterimages behind it: filling while it moves, every sample behind the
ball, draining once the run ends, never accumulating under reduced
motion.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.marble import trail_probe


def _rolled(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("玉転がしゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=trail_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_rolling_marble_streaks_behind_itself() -> None:
    seen = _rolled()

    assert seen["full"] == 10, "the streak never fills"
    assert seen["behind"], "an afterimage sits ahead of the marble"
    assert seen["drained"] is not None, "the stopped marble keeps its streak"


def test_reduced_motion_never_accumulates_one() -> None:
    seen = _rolled(reduced=True)

    assert seen["full"] == 0, "reduced motion still streaks"
