"""A blow on the guardian reads in three beats (§6 観察 2, C-1343).

Flash, smoke that stays, silhouette back out of it - the kaiju leg has
carried the grammar since C-1032, and the guardian is the second boss
built on the same observations. One real strike, sixty frames of facts.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import beat_probe
from sidra_ai.creation.games import generate_game


def _struck(request: str = "迷宮を冒険するゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=beat_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_flash_then_smoke_then_the_silhouette_again() -> None:
    seen = _struck()

    assert seen["hurtAtHit"] > 0, "the blow never flashes"
    assert seen["smokeAtHit"] > seen["hurtAtHit"], "the smoke must outlast the flash"
    assert seen["smokeAfterFlash"] >= 15, "the smoke dies with the flash"
    assert seen["smokeLeft"] == 0, "the smoke never clears"
