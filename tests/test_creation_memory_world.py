"""A trail belongs to the course it was driven on (§8 × §11, C-1732).

Every memory the generated page keeps is stored under a key ending in the
template's name - ``sidra.ghost.racing``, ``sidra.best.racing`` - and
``together.py``'s registry requires exactly that shape, so the keys stay
separable. What nobody had written down is that **one template makes many
games**: C-1107 decided that the same request is the same world and built
the layout from the request's own seed, and the difficulty decides how
long a lap is. Two racing games asked for on different days are two
different courses of two different lengths sharing one key.

Measured before the fix, with two real pages and one store handed from the
first page to the second: after driving A (「レースのゲームを作って」,
easy, LAPS=2), page B (「宇宙のレースゲームを作って」, hard, LAPS=4)
returned ``ghostAt(0) === 562`` - A's x on A's course - as "where you were
here last time", about a course B's player had never driven.

The fix stamps the trail with the world it was driven in and refuses a
trail from any other. The world tag travels **in the value**, not in the
key, so the storage contract is untouched.

Both directions, and the second is the one that keeps the fix honest: a
page that refuses every trail passes the first check on its own, and that
implementation is "delete the ghost".
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.ghost import GHOST_TEMPLATES
from sidra_ai.creation.together import STORAGE_PREFIXES, probe_source
from sidra_ai.creation.tuning import SPEED_BINDING

TEMPLATE = GHOST_TEMPLATES[0]
#: Two games one template makes: a different request (so a different seed,
#: so a different course) and a different difficulty (so, here, a
#: different number of laps).
HERE = ("レースゲームを作って", "normal")
THERE = ("宇宙のレースゲームを作って", "hard")
#: The third page, and the one the destruction battery asked for: the SAME
#: request at a different difficulty. Dropping the difficulty from the world
#: tag left this page sharing HERE's trail, and the pair above could not see
#: it - they differ in the request too, so the seed alone kept them apart.
#: It matters because the trail is banked only on a record (``ghostBank``
#: takes one), and a record set on easy is not a record for hard: in racing
#: that is two laps against four.
HARDER = (HERE[0], "hard")


def _script(request: str, difficulty: str) -> str:
    page = generate_game(request, template=TEMPLATE, difficulty=difficulty).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    return found.group(1)


def _world(script: str) -> str:
    found = re.search(r'GHOST_WORLD=("[^"]*")', script)
    assert found is not None, "the page does not say which world it is"
    return json.loads(found.group(1))


def _run(script: str, stored: dict, frames: int = 900) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive a run")
    source = probe_source(
        script, speed_expr=SPEED_BINDING[TEMPLATE], frames=frames, stored=stored
    ).replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
        f" trail: allStored['sidra.ghost.{TEMPLATE}']||null,",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def drive() -> dict:
    here, there, harder = _script(*HERE), _script(*THERE), _script(*HARDER)
    base = {f"sidra.seen.{TEMPLATE}": "1"}
    first = _run(here, dict(base), frames=3800)
    carried = {**base, f"sidra.ghost.{TEMPLATE}": first["trail"]}
    return {
        "here": here,
        "there": there,
        "first": first,
        "harder": harder,
        "away": _run(there, dict(carried)),
        "awayHarder": _run(harder, dict(carried)),
        "again": _run(here, dict(carried)),
    }


def test_two_games_from_one_template_are_two_worlds(drive: dict) -> None:
    """Otherwise everything below is vacuously true."""

    assert _world(drive["here"]) != _world(drive["there"])
    # The same request at another difficulty is another world too - the
    # course keeps its shape and the run does not (§11's trail is banked
    # only on a record, and a record is per difficulty).
    assert _world(drive["here"]) != _world(drive["harder"])


def test_the_run_that_set_the_record_saved_a_trail(drive: dict) -> None:
    first = drive["first"]
    assert first["trail"], "nothing was banked, so nothing below is being tested"
    assert first["ghost"]["saved"] >= 1


def test_the_trail_says_which_world_it_came_from(drive: dict) -> None:
    stored = json.loads(drive["first"]["trail"])
    assert stored["w"] == _world(drive["here"])
    assert isinstance(stored["t"], list) and stored["t"], stored


def test_another_game_does_not_inherit_the_trail(drive: dict) -> None:
    """(a) The defect: a past self from a course nobody here has driven."""

    ghost = drive["away"]["ghost"]
    assert not ghost["had"], "別のコースの軌跡を自分のものとして読んだ"
    assert ghost["drawn"] == 0, ghost


def test_the_same_request_at_another_difficulty_does_not_inherit_it(drive: dict) -> None:
    """(a), the half the first destruction battery could not see.

    Removing the difficulty from the world tag passed every other check
    here: the other pair differs in its request as well, so the seed alone
    kept those two apart while easy and hard went back to sharing.
    """

    ghost = drive["awayHarder"]["ghost"]
    assert not ghost["had"], "難度違いの走りを自分の記録として読んだ"
    assert ghost["drawn"] == 0, ghost


def test_the_game_it_was_driven_in_still_replays_it(drive: dict) -> None:
    """(b) ...and the fix did not simply switch the ghost off."""

    ghost = drive["again"]["ghost"]
    assert ghost["had"], "自分の世界の軌跡まで読まなくなった"
    assert ghost["drawn"] >= 1, ghost


def test_a_trail_from_before_the_world_was_written_is_forgotten(drive: dict) -> None:
    """The bare array an older page saved names no course, so it is not read.

    Not a migration worth writing: a trail whose course cannot be named is
    exactly the thing this item refuses to draw. The next finished run
    banks a stamped one.
    """

    legacy = json.dumps(json.loads(drive["first"]["trail"])["t"])
    ghost = _run(
        drive["here"],
        {f"sidra.seen.{TEMPLATE}": "1", f"sidra.ghost.{TEMPLATE}": legacy},
    )["ghost"]
    assert not ghost["had"] and ghost["drawn"] == 0, ghost


def test_the_key_shape_did_not_change(drive: dict) -> None:
    """The world tag rides in the value; the registry contract is untouched."""

    assert "sidra.ghost." in STORAGE_PREFIXES
    assert f"'sidra.ghost.'+" in drive["here"]
    for key in drive["first"]["writes"]:
        if key.startswith("sidra.ghost."):
            assert key in (
                f"sidra.ghost.{TEMPLATE}",
                f"sidra.ghost.last.{TEMPLATE}",
            ), key
