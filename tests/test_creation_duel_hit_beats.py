"""A blow on either duelist reads in three beats (§6 観察 2, C-1377).

The kaiju leg has carried flash / lingering smoke / re-emergence since
C-1032, the guardian since C-1343 - and the duel, the third body built
on the same boss grammar, took its blows in one beat. Now both duelists
carry the same numbers (hurt 8, smoke 34), verified by landing one REAL
volley on each: the player's beam through the trigger-time rule, then
the CPU's own volley on a player who stands and takes it.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.duel import beat_probe_source


def _drive() -> dict:
    html = generate_game("ゲームを作って", template="duel").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=beat_probe_source(script),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def blows() -> dict:
    return _drive()


@pytest.mark.parametrize("who", ["e", "p"])
def test_the_blow_lands_and_reads_in_three_beats(blows: dict, who: str) -> None:
    trace = blows[who]
    assert trace, "no blow ever landed - the probe is dead"
    assert trace["hurtFrames"] > 0, "the blow never flashes the body"
    assert trace["smokeFrames"] > 0, "the smoke never lingers"
    assert trace["smokeAfterHurt"] >= 15, (
        f"the smoke dies with the flash ({trace['smokeAfterHurt']} frames past it)"
    )
    assert trace["smokeLeft"] == 0, "the smoke never clears"


def test_both_fighters_actually_lost_a_heart(blows: dict) -> None:
    assert blows["eHp"] < 3 and blows["pHp"] < 3
