"""The HUD is painted, not declared (§4, C-1352).

C-1337's destructions recorded the limit this closes: the contrast judge
reads hudFacts()'s declared constants, so deleting the painting while
keeping the declaration kept full marks. The paint probe reads the last
frame's real fillRect/fillText calls off the running page.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.hudpaint import paint_probe


def _painted(template: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to watch the page paint")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=paint_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_declared_hud_is_really_painted(template: str) -> None:
    seen = _painted(template)
    hud, ops = seen["hud"], seen["ops"]

    assert ops, "the page painted nothing at all"
    plate = [
        o
        for o in ops
        if o["t"] == "r"
        and o["s"].lower() == str(hud["plate"]).lower()
        and abs(o["a"] - hud["alpha"]) < 0.01
    ]
    assert plate, f"the declared plate {hud['plate']} was never filled at {hud['alpha']}"
    ink = [o for o in ops if o["t"] == "t" and o["s"].lower() == str(hud["ink"]).lower()]
    # The declared ink must write ON the declared plate: ink elsewhere on
    # screen (popup numbers, result strips) is a different sentence.
    pairs = [
        (P, T)
        for P in plate
        for T in ink
        if P["x"] - 6 <= T["x"] <= P["x"] + P["w"] + 6
        and P["y"] - 6 <= T["y"] <= P["y"] + P["h"] + 6
    ]
    assert pairs, f"no text in the declared ink {hud['ink']} sits on the plate"
