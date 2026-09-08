"""A thumb slip cannot erase the run (§12 事実 4, C-1397).

The pad's R sits right above A, and seven templates reset unconditionally
mid-run - NN/g's error-prone condition. Now a mid-run tap on the pad's R
sends nothing and resets nothing, a full 30-frame hold paints its receipt
and sends exactly one key pair that really resets, and the end screen
keeps the instant R. The keyboard path is untouched by construction.
"""

from __future__ import annotations

import json
import re
import subprocess

from sidra_ai.creation import generate_game
from sidra_ai.creation.touchpad import padr_probe


def _drive() -> dict:
    html = generate_game("ゲームを作って", template="shooter").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=padr_probe(script),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_a_mid_run_tap_sends_and_erases_nothing() -> None:
    got = _drive()
    assert got["tap"]["sent"] == 0, "the tap leaked a restart key"
    assert got["tap"]["score"] == 777, "a mid-run tap still erases the run"


def test_a_full_hold_gives_a_receipt_and_exactly_one_restart() -> None:
    got = _drive()
    assert got["bar"], "the hold gives no receipt"
    assert got["held"]["down"] == 1 and got["held"]["up"] == 1, (
        "the hold did not send exactly one key pair"
    )
    assert got["held"]["score"] == 0, "the completed hold never resets"


def test_the_end_screen_keeps_the_instant_r() -> None:
    got = _drive()
    assert got["endDown"] == 1 and got["stateAfter"] == "play", (
        "the end screen lost its instant R"
    )
