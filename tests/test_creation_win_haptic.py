"""The finger hears the victory too (§16×§6, C-1399).

winBeat was failBeat's heavier mirror in shake, burst and sound - and the
haptic was wired into the loss alone, so defeat buzzed while victory
stayed silent. Now one line rides every existing guard: the win records a
pattern one step heavier than the hit (the shake pair's own ratio), the
gate still caps the window, and reduced motion or the panel switch
silence it completely.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.juice import win_haptic_probe


def _drive(**kw) -> dict:
    html = generate_game("フルーツキャッチを作って").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=win_haptic_probe(script, **kw),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_win_buzzes_heavier_than_the_loss_and_the_gate_holds() -> None:
    got = _drive()
    assert len(got["pair"]) == 2, "the victory stays silent"
    assert got["pair"][1] > got["pair"][0], "the loss outweighs the win"
    assert got["total"] <= 3, "the gate lets the buzz hammer"


@pytest.mark.parametrize("kw", [{"reduced": True}, {"panel_off": True}])
def test_both_silencers_silence_the_same_win(kw: dict) -> None:
    got = _drive(**kw)
    assert got["total"] == 0, "a silencer failed to silence the win"
