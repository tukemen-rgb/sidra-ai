"""The pad is painted, not declared (§4, C-1390).

C-1388's contrast judge computes ratios from padFacts()' declared colours,
so a page that draws no ring but keeps the declaration would pass - the
C-1337 limit, which C-1352 closed for the HUD. This closes it for the pad:
a style-tracking recording context arms PAD_ON, captures one post-gate
frame, and every padButtons() rect must really receive the plate fill at
the declared alpha, both rings at their declared colours and widths at
full alpha, and its glyph in the declared glyph colour.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.touchpad import padpaint_probe

_THEMES = ("", "紙のテーマで")


def _drive(theme: str) -> dict:
    html = generate_game(f"ゲームを作って {theme}".strip(), template="catch").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=padpaint_probe(script),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("theme", _THEMES)
def test_every_button_gets_plate_rings_and_glyph(theme: str) -> None:
    got = _drive(theme)
    assert got["padOn"], "the coarse pointer never armed the pad"
    assert got["buttons"], "no buttons to paint"
    for b in got["buttons"]:
        assert b["plate"], f"{b['g']}: plate never painted"
        assert b["ringOut"] and b["ringIn"], f"{b['g']}: ring never painted"
        if b["glyph"] is not None:
            assert b["glyph"], f"{b['g']}: glyph never painted"
    assert got["arrowGlyphs"] >= got["arrows"], "arrow glyphs missing"
