"""The crash crushes the car (§1, C-1385).

The hit already had shake, hitstop, the burst and the pace cut - and the
body itself never bent a pixel. Now C-1332's recipe runs on the fifth
body: the strike crushes to 0.7, quarter-steps back and snaps to exactly
1, and under reduced motion the same strike cuts the pace with the
silhouette untouched.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.racing import squash_probe


def _drive(*, reduced: bool) -> dict:
    html = generate_game("ゲームを作って", template="racing").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=squash_probe(script, reduced=reduced),
        capture_output=True, text=True, timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_crash_crushes_and_settles() -> None:
    got = _drive(reduced=False)
    assert got["idle"] == 1, "the cruising car deforms"
    assert got["spdCut"], "the crash never landed"
    assert got["hit"] is not None and got["hit"] <= 0.8, "the crash never crushes"
    assert got["settled"] == 1, "the crush never settles back to shape"


def test_reduced_motion_takes_the_hit_with_a_still_body() -> None:
    got = _drive(reduced=True)
    assert got["spdCut"], "reduced motion must not dodge the crash itself"
    assert got["hit"] == 1 and got["settled"] == 1, "reduced motion still crushes"


def test_the_deformation_reaches_the_silhouette() -> None:
    """C-1636: this probe read the number and not the shape."""

    seen = _drive(reduced=False)

    assert seen["restFills"] > 0
    assert seen["hitDrawn"] > 0, "the crush never reached the silhouette"
    assert seen["idleDrawn"] == 0, "the resting body is drawn deformed"
