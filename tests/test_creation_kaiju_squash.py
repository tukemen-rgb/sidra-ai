"""The struck walker crushes (§1, C-1370).

The walker's hit already had shake, hitstop and knockback; the crush
completes the pair on the one body where the impact never reached the
silhouette. Feet-anchored, quarter-step settle, bit-identical at rest,
and reduced motion never deforms a frame.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import squash_probe


def _blasted(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=squash_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_blast_crushes_and_the_walker_stands_back_up() -> None:
    seen = _blasted()

    assert seen["idleOff"] == 0, "the idle walker deforms"
    assert seen["hitSq"] == 0.7, "the blast never crushes"
    assert seen["settled"] is not None and seen["settled"] <= 30
    assert seen["hp"] == 2, "one blast, one heart"


def test_reduced_motion_never_deforms_a_frame() -> None:
    seen = _blasted(reduced=True)

    assert seen["idleOff"] == 0
    assert seen["hitSq"] == 1, "reduced motion still crushes"
    assert seen["hp"] == 2, "the heart must still be paid"
