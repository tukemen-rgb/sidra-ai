"""The one template with a real distance axis, finally under contract.

§7 観察 7, C-1620. `creation_depth_layers` covered seven templates, and
C-1400's claim excluded this one on the grounds that it was 真上視点 - a
top-down view with no distance. That was simply wrong: marble's `proj()`
is a perspective divide with EYE/FOV/NEAR/FAR and the floor runs to a
horizon at `proj(0,0,FAR)`. All three of §7's planes were already drawn -
the band above the horizon, the floor fading with distance, the marble in
front - so nothing about the picture changes here. What was missing was
the contract, which is what stops a later edit from flattening it.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.marble import fade_probe, probe_source

_THEMES = ("", "紙のテーマで", "ターミナルのテーマで", "dusk のテーマで")


def _lum(hexcolour: str) -> float:
    raw = hexcolour.lstrip("#")
    parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _wcag(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _blend(alpha: float, fg: str, bg: str) -> float:
    f, b = fg.lstrip("#"), bg.lstrip("#")
    out = ""
    for i in (0, 2, 4):
        v = round(int(f[i : i + 2], 16) * alpha + int(b[i : i + 2], 16) * (1 - alpha))
        out += "%02x" % max(0, min(255, v))
    return _lum("#" + out)


def _script(suffix: str = "") -> str:
    html = generate_game(f"玉転がしゲームを作って {suffix}".strip()).html
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


@pytest.mark.parametrize("suffix", _THEMES)
def test_the_far_floor_is_visible_yet_fainter_than_the_near(suffix: str) -> None:
    run = subprocess.run(
        ["node", "-"],
        input=probe_source(_script(suffix)),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    planes = json.loads(run.stdout.strip().splitlines()[-1])["depth"]
    assert len(planes) == 3, "a scene has no far layer"
    for act, plane in enumerate(planes):
        sky = _lum(plane["sky"])
        solid = _lum(plane["solid"])
        far = _blend(plane["alpha"], plane["solid"], plane["sky"])
        assert _wcag(far, sky) >= 1.02, f"act {act}: the far floor is invisible"
        assert _wcag(far, sky) < _wcag(solid, sky), (
            f"act {act}: the far floor is as near as the rung it is made of"
        )


def _painted() -> dict:
    run = subprocess.run(
        ["node", "-"],
        input=fade_probe(_script()),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_floor_really_fades_with_distance() -> None:
    """A declared alpha that never reaches a stroke is not a fade."""

    got = _painted()
    assert got["rungs"] >= 5, f"only {got['rungs']} rungs were drawn"
    assert got["monotone"], "the rungs do not fade with distance"
    assert got["first"] > got["floor"], "the near end is as faint as the far end"
    assert got["last"] == got["floor"], "the far end does not stop at the floor"


def test_the_nearest_body_stays_solid() -> None:
    """Three planes means the front one is not hazed with the back."""

    assert _painted()["nearestSolid"] == 1
