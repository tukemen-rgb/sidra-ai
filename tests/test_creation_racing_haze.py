"""The road had nothing behind it (§7 観察 7, C-1400).

Racing is the template whose distance is literally on the screen - the
top row is the course a car-length-and-then-some ahead - and it was the
last one with a flat backdrop. It now carries the same far-layer contract
as the other six: a static ridge in the theme's own border paint, faded
by FAR_A, laid down before the course so the road runs in front of its
own skyline.

The first prescription was to haze the tarmac itself, and measuring it
killed it: driven, the road and the roadside are 1.012:1 apart on the
default theme. These tests pin the pair that does carry value, and pin
that nothing a driver acts on was faded to get it.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.racing import haze_probe, probe_source

_THEMES = ("", "紙のテーマで", "ターミナルのテーマで", "dusk のテーマで")


def _script(suffix: str = "") -> str:
    html = generate_game(f"レースゲームを作って {suffix}".strip()).html
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


def _drive(source: str) -> dict:
    run = subprocess.run(
        ["node", "-"],
        input=source,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


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


@pytest.mark.parametrize("suffix", _THEMES)
def test_the_ridge_is_visible_yet_fainter_than_its_own_paint(suffix: str) -> None:
    """The contract the judge reads, in every theme and every lap."""

    seen = _drive(probe_source(_script(suffix)))
    planes = seen["depth"]
    assert len(planes) == 3, "a lap has no far layer"
    for act, plane in enumerate(planes):
        sky = _lum(plane["sky"])
        solid = _lum(plane["solid"])
        far = _blend(plane["alpha"], plane["solid"], plane["sky"])
        assert _wcag(far, sky) >= 1.02, f"act {act}: the ridge is invisible"
        assert _wcag(far, sky) < _wcag(solid, sky), (
            f"act {act}: the ridge is as near as the paint it is made of"
        )


def test_the_tarmac_was_the_wrong_thing_to_fade() -> None:
    """Why the first prescription was dropped, kept as a measurement.

    If the road ever separates from the roadside enough to be worth
    hazing, this fails and the choice gets revisited on evidence.
    """

    seen = _drive(probe_source(_script()))
    edge = seen["edge"]
    for act, scene in enumerate(edge["scenes"]):
        road, surf = _lum(scene["road"]), _lum(scene["surf"])
        assert _wcag(road, surf) < 1.2, (
            f"act {act}: the road now stands against the roadside - "
            "re-examine hazing the tarmac itself"
        )


def test_the_ridge_is_painted_behind_the_course() -> None:
    seen = _drive(haze_probe(_script()))
    assert seen["ridgeCount"] == 6, "the skyline never got painted"
    assert seen["ridgeAlphas"] == [seen["far"]], "the ridge is not at FAR_A"
    assert seen["ridgeLow"] <= seen["hz"], "the ridge hangs below the horizon"
    assert seen["ridgeTop"] >= seen["hz"] - seen["ridgeH"], "the ridge overshot"
    assert seen["ridgeLast"] < seen["roadFirst"], (
        "the course does not run in front of its own skyline"
    )


def test_nothing_the_driver_acts_on_is_faded() -> None:
    """§4 keeps its half of the tie: the far layer is scenery, not a veil."""

    seen = _drive(haze_probe(_script()))
    assert seen["rowCount"] > 0 and seen["rowAlphas"] == [1], "the tarmac was faded"
    assert seen["edgeCount"] > 0 and seen["edgeAlphas"] == [1], (
        "the boundary marks were faded"
    )
    # One obstacle was planted out at the horizon and one under the wheels:
    # distance must not decide how solid a hazard looks.
    assert len(seen["obsYs"]) == 2, "the planted obstacles never drew"
    assert min(seen["obsYs"]) < seen["hz"] < max(seen["obsYs"])
    assert seen["obsAlphas"] == [1], "a far obstacle was hazed"
