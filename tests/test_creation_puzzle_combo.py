"""The puzzle's run rides the clears, never the square (§13, C-1436).

COMBO_UNWIRED held puzzle back: a multiplier would compound the squared
size bonus. C-1420's sum answers it on the fifth template - the run
multiplies the clear's base (one per tile), the size bonus rides outside
it, and a x1 clear pays exactly cells squared, the payment this game
always made.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.combo import COMBO_TEMPLATES, COMBO_UNWIRED
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.puzzle import combo_probe


def test_puzzle_moved_from_unwired_to_wired() -> None:
    assert "puzzle" in COMBO_TEMPLATES
    assert "puzzle" not in COMBO_UNWIRED


@pytest.fixture(scope="module")
def played() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the board")
    page = generate_game("さめがめ風パズルを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=combo_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_every_payment_is_base_times_mult_plus_size_bonus(played: dict) -> None:
    clears = played["clears"]
    assert len(clears) >= 5
    for c in clears:
        assert c["paid"] == c["mult"] * c["size"] + c["size"] ** 2 - c["size"], c


def test_the_ladder_climbs_and_x1_is_the_old_identity(played: dict) -> None:
    assert max(c["mult"] for c in played["clears"]) >= 2, "the run never climbed"
    # A x1 clear pays exactly cells squared - the payment this game always
    # made, which is what lets the wiring in without moving the economy.
    for c in played["clears"]:
        if c["mult"] == 1:
            assert c["paid"] == c["size"] ** 2


def test_an_invalid_tap_breaks_the_run_and_x1_resumes(played: dict) -> None:
    assert played["broke"] == {
        "run": 0, "mult": 1,
        "step": played["broke"]["step"], "max": played["broke"]["max"]}
    after = played["afterBreak"]
    assert after is not None
    assert after["mult"] == 1
    assert after["paid"] == after["size"] ** 2
