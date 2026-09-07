"""Being hit stays visible without motion (§4×§15, C-1386).

The adventure's mercy window was told only by the inv blink - a motion
effect the reduced-motion contract removes, leaving the reduced hero hit
with no visible state at all. Now one real hit costs a heart in both
motions; normal motion keeps the blink (gaps in the hero's draw) with no
outline, and reduced motion holds a steady outline for the mercy window
and drops it exactly when the window closes.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.adventure import hurt_probe


def _drive(*, reduced: bool) -> dict:
    html = generate_game("ゲームを作って", template="adventure").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=hurt_probe(script, reduced=reduced),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("reduced", [False, True])
def test_the_hit_lands_in_both_motions(reduced: bool) -> None:
    got = _drive(reduced=reduced)
    assert got["hpAfter"] == 2, "the hit never cost a heart"
    assert got["invAfter"] == 60, "the mercy window never opened"


def test_normal_motion_keeps_the_blink_without_the_outline() -> None:
    got = _drive(reduced=False)
    assert got["outlineFrames"] == 0, "normal motion shows the reduced outline"
    assert got["blinkGaps"] > 0, "the blink is gone"


def test_reduced_motion_holds_a_steady_outline_for_the_window() -> None:
    got = _drive(reduced=True)
    assert got["outlineFrames"] >= 50, (
        "the mercy window is invisible without motion"
    )
    assert got["outlineAfter"] == 0, "the outline outlives the window"
