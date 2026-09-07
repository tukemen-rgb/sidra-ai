"""The struck hero crushes (§1, C-1387).

The adventure's hit had shake, hitstop, knockback, the burst, the blink
and C-1386's reduced outline - and the hero itself never moved a pixel of
silhouette. Now one real contact hit sinks the hero to 0.7 through the
squash channel, the hat bar's recorded dims follow the bottom-anchored
joint transform (the crush provably reaches the paint), the crush settles
back to exactly 1 within half a second, and under reduced motion the same
hit lands with the outline unchanged.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.adventure import squash_probe


def _drive(*, reduced: bool) -> dict:
    html = generate_game("ゲームを作って", template="adventure").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=squash_probe(script, reduced=reduced),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("reduced", [False, True])
def test_the_idle_hero_holds_its_shape_and_the_hit_lands(reduced: bool) -> None:
    got = _drive(reduced=reduced)
    assert got["idleOff"] == 0, "the idle hero deforms"
    assert got["hp"] == 2, "the hit never cost exactly one heart"


def test_one_hit_crushes_reaches_the_paint_and_settles() -> None:
    got = _drive(reduced=False)
    assert got["hitSq"] == 0.7, "the hit never crushes"
    assert got["crushedDrawn"] > 0, "the crush never reaches the paint"
    assert got["settled"] is not None and got["settled"] <= 30, (
        "the crush never settles"
    )
    assert got["restSq"] == 1


def test_reduced_motion_takes_the_hit_with_a_still_body() -> None:
    got = _drive(reduced=True)
    assert got["hitSq"] == 1, "reduced motion still crushes"
    assert got["restSq"] == 1
