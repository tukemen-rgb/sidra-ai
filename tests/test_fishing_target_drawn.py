"""C-1206: the fishing target must be drawn, not merely animated.

The default template's target was ``sprite('target',...,'')`` - on a
standalone page (every page chat produces) the empty fallback drew nothing,
while the code computed a bob offset for it every frame. The other three
empty-fallback sprite slots (shooter's foe, adventure's rock, duel's
fighter) all sit over a procedural body; fishing alone had none.

Verified by playing the page in node with a recording context: a filled
body and tail have to land inside the band the page itself painted, so a
fish drawn in the wrong place fails too.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from sidra_ai.creation.games import generate_game

_PROBE_PATTERN = re.compile(r'_FISHING_DRAW_PROBE = """(.*?)"""', re.S)
_METRICS = Path(__file__).resolve().parent.parent / "scripts" / "product_metrics.py"


def _probe_source() -> str:
    text = _METRICS.read_text(encoding="utf-8")
    match = _PROBE_PATTERN.search(text)
    assert match, "the fishing draw probe has left product_metrics.py"
    return match.group(1)


def test_fishing_page_draws_body_and_tail_inside_the_band():
    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is not installed")

    page = generate_game("ゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None

    result = subprocess.run(
        ["node", "-"],
        input=_probe_source().replace("SCRIPT_PLACEHOLDER", script.group(1)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[:200]
    seen = json.loads(result.stdout)
    assert seen["band"], "the page no longer paints its zone band"
    assert seen["bodyInBand"], "no filled body lands inside the band"
    assert seen["tailInBand"], "the fish has no tail"


def test_fish_is_painted_under_the_asset_slot():
    """A real asset in the 'target' slot must still win over the fallback."""

    html = generate_game("釣りゲームを作って").html
    fish = html.index("cx.ellipse(fx+3,fy")
    slot = html.index("sprite('target'")
    assert fish < slot
