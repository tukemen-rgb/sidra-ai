"""The fight leaves a trace (§23, C-1374).

Nijman's technique list carries permanence as its own entry: corpses,
debris, shells - the consequences of the player's actions stay visible.
Before this, the shooter's foe left the array on its death frame and the
adventure's enemy stopped being drawn the moment ``alive`` flipped: once
the burst faded, the world remembered nothing.

Driven, not read: an enemy is killed with the real sword, the room is
left and re-entered; a hull is shot down and its chunks watched falling.
"""

from __future__ import annotations

import json
import re
import subprocess

from sidra_ai.creation import generate_game
from sidra_ai.creation.adventure import wreck_probe as adv_wreck
from sidra_ai.creation.shooter import wreck_probe as sh_wreck


def _script(template: str) -> str:
    html = generate_game("ゲームを作って", template=template).html
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


def _run(source: str) -> dict:
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=180
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_a_slain_enemy_leaves_a_husk_where_it_fell() -> None:
    got = _run(adv_wreck(_script("adventure")))
    assert got["before"] == 0
    marks = got["afterKill"]["marks"]
    assert len(marks) == 1, "the kill left no husk"
    assert abs(marks[0]["x"] - got["enemyAt"]["x"]) <= 24
    assert abs(marks[0]["y"] - got["enemyAt"]["y"]) <= 24
    assert got["aliveNow"] == 2, "the sword killed more (or less) than one"


def test_the_husk_survives_leaving_the_room() -> None:
    """Walk away and come back: still there - Nijman's own example."""

    got = _run(adv_wreck(_script("adventure")))
    assert got["awayMarks"] == 0, "the village shows the cave's dead"
    assert len(got["back"]["marks"]) == 1, "leaving the room erased the husk"


def test_the_fallen_guardian_leaves_a_wreck_too() -> None:
    got = _run(adv_wreck(_script("adventure")))
    assert got["guardWreck"] is True


def test_a_downed_hull_drops_chunks_that_fall_and_drain() -> None:
    got = _run(sh_wreck(_script("shooter")))
    assert got["spawned"] == 3, "the kill dropped no chunks"
    assert all(b > a for a, b in zip(got["y0"], got["y1"])), "the chunks hang"
    assert got["drained"] == 0, "the chunks never leave the screen"


def test_reduced_motion_drops_no_chunks() -> None:
    got = _run(sh_wreck(_script("shooter"), reduced=True))
    assert got["spawned"] == 0, "reduced motion still drops falling chunks"


def test_declared_and_painted_read_the_same_constant() -> None:
    """The shared-constant guard (C-1342 family): both templates paint
    the wreckage through WRECK_A and report the same value as facts."""

    for template in ("adventure", "shooter"):
        script = _script(template)
        assert "WRECK_A" in script
        assert "cx.globalAlpha=WRECK_A" in script, f"{template} paints without it"
