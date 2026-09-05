"""The key that is a fact, not an item (§3, C-1340).

§3's lock-and-key taxonomy includes knowledge, and distinguishes hard
locks from soft ones a knowing player can route around. The cave key was
a hard lock with one edge - kill every enemy. The forest stone now tells
a seeded order, and knocking the cave's three marks in that order breaks
the key's seal without a fight. The probe learns the order the way a
player does: by striking the stone and reading what it says.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import know_probe
from sidra_ai.creation.games import generate_game


def _knocked(request: str = "迷宮を冒険するゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=know_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def knocked() -> dict:
    return _knocked()


def test_the_stone_speaks_the_whole_order(knocked: dict) -> None:
    assert sorted(knocked["order"]) == [0, 1, 2], knocked["signMsg"]
    assert "の順に" in knocked["signMsg"]


def test_a_wrong_knock_leaves_the_seal_shut(knocked: dict) -> None:
    assert knocked["wrongProgress"] == 0
    assert knocked["wrongDrop"] is False


def test_the_right_order_frees_the_key_without_a_fight(knocked: dict) -> None:
    assert knocked["solved"] is True
    assert knocked["dropped"] is True
    assert knocked["keyGained"] is True
    # The soft route's whole point: the enemies never had to die.
    assert knocked["aliveAtSolve"] == knocked["aliveBefore"] > 0
