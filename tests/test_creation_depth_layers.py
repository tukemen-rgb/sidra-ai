"""The far layer is far (§7 観察 7, C-1342).

Distance is drawn by contrast - foreground silhouette, midground subject,
faded far layer - and the film pairs it with §6's partial-view scale. The
kaiju arena was a flat sky behind the one template whose whole subject is
scale. The page reports its depth contract, and these tests blend the
skyline over each scene's sky the way the canvas does: visibly there, yet
fainter than the midground silhouette, in every scene.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import probe_source


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
    return "#%02x%02x%02x" % tuple(round(alpha * a + (1 - alpha) * b) for a, b in zip(t, u))


def _fought(suffix: str = "") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(f"巨大怪獣と戦うゲームを作って {suffix}".strip()).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("suffix", ["", "紙のテーマで"])
def test_the_skyline_sits_between_sky_and_silhouette(suffix: str) -> None:
    seen = _fought(suffix)

    depth = seen["depth"]
    assert len(depth) == 3, "three scenes, three skies"
    for act, plane in enumerate(depth):
        far = _lum(_blend(plane["alpha"], plane["solid"], plane["sky"]))
        sky = _lum(plane["sky"])
        solid = _lum(plane["solid"])
        assert _wcag(far, sky) >= 1.02, f"act {act}: the far layer is invisible"
        assert _wcag(far, sky) < _wcag(solid, sky), (
            f"act {act}: the far layer is as near as the leg"
        )
