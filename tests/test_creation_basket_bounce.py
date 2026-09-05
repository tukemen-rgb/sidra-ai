"""The basket takes the impact in its shape (§1, C-1341).

Squash & stretch's receiving half: the catch basket meets an impact every
second and was the only rigid body left in its frame. Watched on a real
catch - 1 at rest, below 0.9 on the catch frame, back to 1 within half a
second - and bit-identical 1 under reduced motion, which is C-1332's line
verbatim: the silhouette never changes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.catchgame import bounce_probe
from sidra_ai.creation.games import generate_game


def _watched(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("キャッチゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=bounce_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_catch_squashes_and_the_rest_holds_its_shape() -> None:
    seen = _watched()

    assert seen["caught"], "nothing was ever caught, so nothing was measured"
    assert seen["idleOff"] == 0, "the basket deforms with nothing landing"
    assert seen["catchSq"] is not None and seen["catchSq"] < 0.9
    assert seen["settled"] == 1, f"the bounce never settles ({seen['settled']})"


def test_reduced_motion_keeps_the_silhouette() -> None:
    seen = _watched(reduced=True)

    assert seen["caught"], "nothing was ever caught, so nothing was measured"
    assert seen["idleOff"] == 0
    assert seen["catchSq"] == 1
    assert seen["minAfter"] == 1
