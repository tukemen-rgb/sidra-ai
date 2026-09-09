"""The hull took the heaviest hit and kept its shape (§1, C-1601).

§1's technique list puts "拡縮バウンス" and "被弾時のヒットストップと
ノックバック" side by side. The shooter's ram already had the second half
and more of it than any other template - shake 11, five frames of
hitstop, a knockback and an eighteen-particle burst - and was the one
body in the ten templates that never deformed.

The crush is racing's: 0.7, settling by quarter-steps, silent under
reduced motion. These tests pin that the recoil still only moves the ship
rather than bending it, and that the deformation reaches the paint rather
than living in a variable.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.shooter import squash_probe


def _drive(*, reduced: bool = False) -> dict:
    html = generate_game("シューティングゲームを作って").html
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


def test_the_ram_crushes_the_hull() -> None:
    got = _drive()
    assert got["hp"] == 2, "the engineered ram never landed"
    assert got["hitSq"] < 0.9, "the heaviest hit in the game left the shape alone"


def test_the_crush_reaches_the_paint() -> None:
    """A number that never changes a drawn coordinate is not a deformation."""

    got = _drive()
    assert got["restW"] is not None and got["hitW"] is not None
    assert got["hitW"] > got["restW"], "the hull triangle never widened"
    # Bottom-anchored: it squats and spreads by the same budget.
    assert got["hitW"] == pytest.approx(got["restW"] * (2 - got["hitSq"]))


def test_flying_and_firing_does_not_deform_the_hull() -> None:
    """C-1380's recoil moves the ship; it must not bend it."""

    got = _drive()
    assert got["restShots"] > 0, "the probe never actually fired - it proves nothing"
    assert got["restSq"] == [1], "the untouched hull deformed"
    assert got["restShapes"] == 1, "the drawn hull changed size without a hit"


def test_the_crush_settles() -> None:
    got = _drive()
    assert 0 <= got["settledIn"] <= 30, f"still crushed after {got['settledIn']} frames"
    assert got["settled"] == 1


def test_reduced_motion_never_bends_the_silhouette() -> None:
    got = _drive(reduced=True)
    assert got["hp"] == 2, "the ram must still cost a life"
    assert got["hitSq"] == 1, "reduced motion still crushes"
    assert got["restSq"] == [1]
    assert got["hitW"] == pytest.approx(got["restW"]), "the drawn hull moved anyway"
