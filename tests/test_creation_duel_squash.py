"""The fighter's body under its impacts (§1, C-1358).

The jump got squash & stretch in C-1332 and the basket in C-1341, and the
duel - whose whole loop is the exchange of impacts - stayed rigid. Three
verbs on the player's own keys: the held charge sinks the pose, the
release snaps it tall, a taken volley crushes it - each settling back
within half a second. Under reduced motion the silhouette never changes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.duel import squash_probe
from sidra_ai.creation.games import generate_game


def _fought(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("光線で撃ち合う対戦ゲームを作って").html
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


@pytest.fixture(scope="module")
def fought() -> dict:
    return _fought()


def test_the_charge_sinks_and_the_release_snaps_tall(fought: dict) -> None:
    assert fought["idleOff"] == 0, "the fighter breathes with nobody acting"
    assert fought["chargeDip"] < 0.97, "the held charge never sinks the pose"
    assert fought["released"] > 1.1, "the release never snaps tall"
    assert fought["settleFire"] == pytest.approx(1, abs=0.02)


def test_the_taken_volley_crushes_and_settles(fought: dict) -> None:
    assert fought["gotHit"], "no volley ever landed, so the crush went unmeasured"
    assert fought["hitSq"] is not None and fought["hitSq"] < 0.9
    assert fought["settleHit"] == pytest.approx(1, abs=0.02)


def test_reduced_motion_keeps_the_silhouette() -> None:
    fought = _fought(reduced=True)

    assert fought["gotHit"]
    assert fought["idleOff"] == 0
    assert fought["chargeDip"] == 1
    assert fought["released"] == 1
    assert fought["hitSq"] == 1


def test_the_deformation_reaches_the_silhouette() -> None:
    """C-1636: this probe read the number and not the shape."""

    seen = _fought()

    assert seen["restFills"] > 0
    assert seen["chargeDrawn"] > 0, "the crush never reached the silhouette"
    assert seen["idleDrawn"] == 0, "the resting body is drawn deformed"
