"""A lock only skill opens (§3, C-1367).

Hard locks open by their key; soft locks answer to skill. A shelf hangs
56px over the highest platform of the middle stretch - inside a held
jump's reach from that base, outside it from everywhere lower - with two
gems on it, and the low road still runs to the flag underneath it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import route_probe


def _driven(request: str, *, drive: int = 2400) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=route_probe(script.group(1), drive=drive),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def default_run() -> dict:
    return _driven("ジャンプで進むゲームを作って")


def test_the_low_road_bypasses_the_shelf(default_run: dict) -> None:
    assert default_run["goal"], "the low road never reaches the flag"
    assert not default_run["boarded"], "the auto-runner boards the shelf"
    assert not any(default_run["lowGems"]), "the low road collects the shelf's gems"


def test_the_standing_jump_opens_the_lock(default_run: dict) -> None:
    assert default_run["onFirst"], "the standing jump never boards the shelf"
    assert all(default_run["highGems"]), "the shelf keeps its gems"


def test_low_ground_falls_short(default_run: dict) -> None:
    assert default_run["shortBy"] <= -6, "the lock opens from low ground"


def test_the_hard_course_carries_the_same_shelf() -> None:
    """Geometry only: hard's widened gaps outrun the one-rule pilot."""

    seen = _driven("ジャンプで進むゲームを作って 難しくして", drive=0)
    assert seen["onFirst"] and all(seen["highGems"])
    assert seen["shortBy"] <= -6
