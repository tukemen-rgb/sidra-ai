"""The second ghost, and the wall it must not touch (§11 事実 1, C-1333).

The Bath result §11 records is about racing a GROUP - multiple ghosts
doubled the gains - and a group of one is not one. The second ghost is
the run before this one, saved on every finished run somebody played,
while the best trail still moves only on a record: a defeat that
overwrote it would replace the wall with the stumble.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.together import probe_source
from sidra_ai.creation.tuning import SPEED_BINDING


def _run(script: str, stored: dict) -> dict:
    source = probe_source(
        script, speed_expr=SPEED_BINDING["racing"], frames=3800, stored=stored
    ).replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
        " trail: allStored['sidra.ghost.racing']||null,"
        " lastTrail: allStored['sidra.ghost.last.racing']||null,"
        " score: roundFacts().score,",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_defeated_run_becomes_the_second_ghost_and_spares_the_record() -> None:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive three runs")
    page = generate_game("レースゲームを作って", template="racing").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    script = found.group(1)

    base = {"sidra.seen.racing": "1"}
    first = _run(script, dict(base))
    assert not first["ghost"]["lastHad"] and first["ghost"]["lastDrawn"] == 0
    assert first["trail"] and first["lastTrail"], "the first run saved both trails"

    slow = round(first["atLoad"]["speed"] * 0.55, 2)
    carry = {
        **base,
        "sidra.ghost.racing": first["trail"],
        "sidra.ghost.last.racing": first["lastTrail"],
        "sidra.best.racing": str(first["score"]),
        "sidra.tune.racing": {"speed": slow},
    }
    second = _run(script, dict(carry))
    assert second["score"] < first["score"], "the slowed run must not set a record"
    assert second["ghost"]["drawn"] >= 1 and second["ghost"]["lastDrawn"] >= 1, (
        "both ghosts must run beside the slowed run"
    )
    assert second["trail"] == first["trail"], "a defeat overwrote the record's trail"
    assert second["lastTrail"] and second["lastTrail"] != first["lastTrail"], (
        "the defeat did not become tomorrow's second ghost"
    )

    off = _run(script, {**carry, "sidra.tune.racing": {"speed": slow, "ghost": False}})
    assert off["ghost"]["drawn"] == 0 and off["ghost"]["lastDrawn"] == 0
    assert off["ghost"]["runHash"] == second["ghost"]["runHash"], (
        "the second ghost changed how the race went"
    )
