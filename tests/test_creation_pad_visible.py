"""The pad stays visible on every floor (§4 WCAG 1.4.11, C-1388).

The virtual pad is the phone's only control, and its buttons sit on
whatever the scene floor is this act. Border-on-raised measured 1.05:1 on
paper - near invisible. The dual ring (surface outside, ink inside, both
full alpha) must clear 3:1 through its better half on every theme's every
act, and the ink glyph must clear 3:1 on the alpha-blended plate.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.touchpad import pad_probe

_THEMES = ("", "紙のテーマで", "ターミナルのテーマで", "dusk のテーマで")


def _lum(hexcolour: str) -> float:
    raw = hexcolour.lstrip("#")
    parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _wcag(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _blend(alpha: float, top: str, under: str) -> str:
    t = [int(top.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    u = [int(under.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(
        round(alpha * a + (1 - alpha) * b) for a, b in zip(t, u)
    )


def _drive(theme: str) -> dict:
    html = generate_game(f"ゲームを作って {theme}".strip(), template="catch").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    floor = re.search(r"sky:scenePaint\('(#[0-9a-f]{6})'\)", script).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=pad_probe(script, floor_token=floor),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("theme", _THEMES)
def test_the_ring_pair_clears_three_to_one_on_every_floor(theme: str) -> None:
    got = _drive(theme)
    facts = got["facts"]
    assert len(got["floors"]) == 3 and all(got["floors"])
    for act, under in enumerate(got["floors"]):
        ring = max(
            _wcag(_lum(facts["ringIn"]), _lum(under)),
            _wcag(_lum(facts["ringOut"]), _lum(under)),
        )
        assert ring >= 3.0, f"act {act}: the boundary melts ({ring:.2f})"


@pytest.mark.parametrize("theme", _THEMES)
def test_the_glyph_clears_three_to_one_on_the_blended_plate(theme: str) -> None:
    got = _drive(theme)
    facts = got["facts"]
    for act, under in enumerate(got["floors"]):
        glyph = _wcag(
            _lum(facts["glyph"]),
            _lum(_blend(facts["alpha"], facts["plate"], under)),
        )
        assert glyph >= 3.0, f"act {act}: the glyph sinks ({glyph:.2f})"
