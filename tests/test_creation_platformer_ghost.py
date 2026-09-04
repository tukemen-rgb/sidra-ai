"""The platformer's past self, met at the same point of the course.

C-1330 wires C-1401's trail to its third template, answering the note
that parked it ("progress is x, but the camera moves"): the course x is
the progress, the HEIGHT is the stored value, and the ghost is drawn at
the hero's own screen x at the height the record run had here - so "they
were on the ledge while I am in the pit" reads exactly where the player
is looking. The contract is the shared one: a memory, not a second hero.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.ghost import GHOST_TEMPLATES
from sidra_ai.creation.together import probe_source
from sidra_ai.creation.tuning import SPEED_BINDING


def test_the_platformer_is_a_ghost_course_now() -> None:
    assert "platformer" in GHOST_TEMPLATES


def _run(script: str, stored: dict) -> dict:
    source = probe_source(
        script, speed_expr=SPEED_BINDING["platformer"], frames=3800, stored=stored
    ).replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
        " trail: allStored['sidra.ghost.platformer']||null,",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_second_run_meets_a_ghost_that_touches_nothing() -> None:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive three runs")
    page = generate_game("ジャンプアクションを作って", template="platformer").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    script = found.group(1)

    base = {"sidra.seen.platformer": "1"}
    first = _run(script, dict(base))
    assert not first["ghost"]["had"], "a ghost stood beside the very first run"
    assert first["ghost"]["drawn"] == 0
    assert first["trail"] and first["ghost"]["saved"] >= 1, "the record saved no trail"

    carried = {**base, "sidra.ghost.platformer": first["trail"]}
    second = _run(script, dict(carried))
    assert second["ghost"]["had"] and second["ghost"]["drawn"] >= 1
    assert second["geometry"] != first["geometry"], "the ghost was never drawn"

    off = _run(script, {**carried, "sidra.tune.platformer": {"ghost": False}})
    assert off["ghost"]["drawn"] == 0, "the switch does not put the ghost away"
    assert off["ghost"]["runHash"] == second["ghost"]["runHash"], (
        "the ghost changed how the run went"
    )
    assert off["geometry"] == first["geometry"], (
        "with the ghost off the page still drew differently"
    )
