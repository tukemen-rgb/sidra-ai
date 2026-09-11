"""The other four ladders (§1, C-1652).

C-1648 put two templates under the proportionality half of Vlambeer's rule
and said plainly that seven use two or more weights. These are the four it
left: each needed a run of its own, because unlike the short rosters of
C-1637/1640/1645 the probe did not already exist - the two events had to be
driven. A hard landing against a fall, an ordinary gate against a hot one,
a foe downed against the hull rammed, a beam over-charged against a beam
taken.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.duel import ladder_probe as duel_ladder
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.marble import ladder_probe as marble_ladder
from sidra_ai.creation.platformer import ladder_probe as plat_ladder
from sidra_ai.creation.shooter import ladder_probe as shooter_ladder

CASES = (
    ("ジャンプで進むゲームを作って", plat_ladder, "platformer"),
    ("玉転がしゲームを作って", marble_ladder, "marble"),
    ("シューティングゲームを作って", shooter_ladder, "shooter"),
    ("ビームで撃ち合うゲームを作って", duel_ladder, "duel"),
)


def _kicks(request: str, builder) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=builder(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(("request_", "builder", "name"), CASES, ids=[c[2] for c in CASES])
def test_both_events_actually_happened(request_, builder, name) -> None:
    """A pair that never fired is not a pass (C-1637)."""

    seen = _kicks(request_, builder)

    assert seen["light"] is not None, f"{name}: the light event never fired"
    assert seen["heavy"] is not None, f"{name}: the heavy event never fired"
    assert seen["light"]["kick"] > 0, name
    assert seen["heavy"]["kick"] > 0, name


@pytest.mark.parametrize(("request_", "builder", "name"), CASES, ids=[c[2] for c in CASES])
def test_the_heavier_event_kicks_harder(request_, builder, name) -> None:
    seen = _kicks(request_, builder)

    assert seen["heavy"]["kick"] > seen["light"]["kick"], (name, seen)
