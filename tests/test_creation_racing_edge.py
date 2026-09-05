"""The road's edge survives every paint (§4, C-1347).

The roadside ticks and the start/finish band are the boundary between
"on the road" and "losing speed" - information, not decoration. One
fixed light neutral sat at ~1.05:1 against everything on the paper
theme. The mark is a two-tone pair now, and in every scene one half must
clear the 3:1 component floor against both the road and the roadside.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.racing import probe_source


def _lum(hexcolour: str) -> float:
    raw = hexcolour.lstrip("#")
    parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _wcag(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _raced(suffix: str = "") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(f"レースゲームを作って {suffix}".strip()).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("suffix", ["", "紙のテーマで"])
def test_one_half_of_the_pair_always_stands(suffix: str) -> None:
    edge = _raced(suffix)["edge"]

    lum_a, lum_b = _lum(edge["a"]), _lum(edge["b"])
    assert _wcag(lum_a, lum_b) >= 3.0, "the pair cannot read against itself"
    assert len(edge["scenes"]) == 3
    for act, plane in enumerate(edge["scenes"]):
        for side in ("surf", "road"):
            ground = _lum(plane[side])
            best = max(_wcag(lum_a, ground), _wcag(lum_b, ground))
            assert best >= 3.0, f"act {act}: the edge sinks into {side} ({best:.2f})"
