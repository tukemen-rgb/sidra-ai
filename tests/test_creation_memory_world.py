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

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.ghost import GHOST_TEMPLATES
from sidra_ai.creation.together import (
    DEVICE_WIDE,
    STORAGE_PREFIXES,
    WORLD_SCOPED,
    probe_source,
    unstamped_writes,
)
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
    found = re.search(r'MEM_WORLD=("[^"]*")', script)
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
        " best: roundBestRead(), row: roundLogFacts().stored,"
        f" trail: allStored['sidra.ghost.{TEMPLATE}']||null,"
        f" storedBest: allStored['sidra.best.{TEMPLATE}']||null,"
        f" storedRow: allStored['sidra.runs.{TEMPLATE}']||null,",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


#: The pilot scores the same number in either world, so a quiet store
#: cannot tell "refused" from "happened to match". These two are loud.
LOUD_BEST = 999
LOUD_ROW = [111, 222]


@pytest.fixture(scope="module")
def drive() -> dict:
    here, there, harder = _script(*HERE), _script(*THERE), _script(*HARDER)
    base = {f"sidra.seen.{TEMPLATE}": "1"}
    first = _run(here, dict(base), frames=3800)
    carried = {**base, f"sidra.ghost.{TEMPLATE}": first["trail"]}
    loud = {
        **base,
        f"sidra.ghost.{TEMPLATE}": json.loads(first["trail"]),
        f"sidra.best.{TEMPLATE}": {"w": _world(here), "v": LOUD_BEST},
        f"sidra.runs.{TEMPLATE}": {"w": _world(here), "v": list(LOUD_ROW)},
    }
    return {
        "here": here,
        "there": there,
        "loudMine": _run(here, dict(loud), frames=240),
        "loudAway": _run(there, dict(loud), frames=240),
        "loudHarder": _run(harder, dict(loud), frames=240),
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


def test_every_memory_of_a_run_says_which_world_it_came_from(drive: dict) -> None:
    """One shape for all of them: the trail, the best and the row.

    Two shapes would be how this drifts apart again - C-1732 stamped the
    trail and left the number, and for one cycle the page refused to draw
    the trail of the very run whose number it was still showing.
    """

    here = _world(drive["here"])
    for what in ("trail", "storedBest", "storedRow"):
        box = json.loads(drive["first"][what])
        assert box["w"] == here, (what, box)
        assert box["v"] not in (None, [], ""), (what, box)
    assert isinstance(json.loads(drive["first"]["trail"])["v"], list)


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


def test_a_memory_from_before_the_world_was_written_is_adopted_once(drive: dict) -> None:
    """An unstamped value is claimed by the first page to read it.

    Refusing it was the first answer (C-1732 refused the trail), and what
    changed it is what refusing costs: every player who had a record
    before this shipped loses it, and the ordinary single-game player
    loses everything for a bleed that could never have reached them. So
    the page claims it and stamps it on the spot - the window in which the
    wrong game can claim it is one load, and it closes itself.
    """

    old = json.loads(drive["first"]["trail"])["v"]
    run = _run(
        drive["here"],
        {
            f"sidra.seen.{TEMPLATE}": "1",
            f"sidra.ghost.{TEMPLATE}": old,
            f"sidra.best.{TEMPLATE}": LOUD_BEST,
            f"sidra.runs.{TEMPLATE}": list(LOUD_ROW),
        },
        frames=240,
    )
    assert run["ghost"]["had"], "印の無い軌跡を、誰も引き取らずに捨てた"
    assert run["best"] == LOUD_BEST and run["row"] == LOUD_ROW, run
    # ...and the claim is written down, so the next game cannot claim it.
    for what in ("storedBest", "storedRow", "trail"):
        box = json.loads(run[what])
        assert box["w"] == _world(drive["here"]), (what, box)


def test_an_adopted_memory_does_not_reach_the_next_game(drive: dict) -> None:
    """The one load the window is open for, closed by the load itself."""

    old = json.loads(drive["first"]["trail"])["v"]
    bare = {
        f"sidra.seen.{TEMPLATE}": "1",
        f"sidra.ghost.{TEMPLATE}": old,
        f"sidra.best.{TEMPLATE}": LOUD_BEST,
        f"sidra.runs.{TEMPLATE}": list(LOUD_ROW),
    }
    claimed = _run(drive["here"], dict(bare), frames=240)
    after = {
        f"sidra.seen.{TEMPLATE}": "1",
        f"sidra.ghost.{TEMPLATE}": json.loads(claimed["trail"]),
        f"sidra.best.{TEMPLATE}": json.loads(claimed["storedBest"]),
        f"sidra.runs.{TEMPLATE}": json.loads(claimed["storedRow"]),
    }
    run = _run(drive["there"], after, frames=240)
    assert not run["ghost"]["had"], "引き取り済みの軌跡が別のゲームへ漏れた"
    assert run["best"] != LOUD_BEST and run["row"] != LOUD_ROW, run


def test_another_game_does_not_inherit_the_best_or_the_row(drive: dict) -> None:
    """The half C-1732 left undone, and the reason this item exists.

    For one cycle the page refused to draw the trail of the very run whose
    number it was still calling this course's best - a four-lap course
    telling the player their best here is a two-lap time.
    """

    for name in ("loudAway", "loudHarder"):
        run = drive[name]
        assert run["best"] != LOUD_BEST, f"{name}: 別の世界の自己ベストを読んだ"
        assert run["row"] != LOUD_ROW, f"{name}: 別の世界の履歴を読んだ"


def test_the_game_it_was_driven_in_still_has_its_best_and_row(drive: dict) -> None:
    """...and the fix is not "forget everything"."""

    run = drive["loudMine"]
    assert run["best"] == LOUD_BEST
    assert run["row"] == LOUD_ROW


def test_every_registered_key_says_which_kind_of_memory_it_is() -> None:
    """C-1729's lesson: the list that decides is no use without the rest.

    A key that is neither world-scoped nor deliberately device-wide is a
    key nobody has thought about, and the next feature to pick it inherits
    whichever answer the code happened to give.
    """

    for prefix in STORAGE_PREFIXES:
        in_world, in_device = prefix in WORLD_SCOPED, prefix in DEVICE_WIDE
        assert in_world != in_device, prefix
    assert not set(WORLD_SCOPED) & set(DEVICE_WIDE)
    assert not (set(WORLD_SCOPED) | set(DEVICE_WIDE)) - set(STORAGE_PREFIXES)
    for prefix, why in DEVICE_WIDE.items():
        assert len(why) > 20, f"{prefix} を端末ごとにする理由が書かれていない"


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_write_to_a_world_scoped_key_carries_the_stamp(template: str) -> None:
    """Read at the source, because the run time cannot see this.

    ``memRead`` adopts an unstamped value and re-stamps it, so a page that
    wrote bare numbers would have its own later reads tidy the evidence
    away inside the same round - the destruction battery walked straight
    through the run-time version of this check. What the page WRITES is
    not something a page can hide from a reader of its own source.
    """

    page = generate_game("ゲームを作って", template=template).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    assert unstamped_writes(found.group(1)) == []


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
