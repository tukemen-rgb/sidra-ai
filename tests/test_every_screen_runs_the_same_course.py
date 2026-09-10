"""C-1628: the one screen that disagreed was the one nothing compared.

``creation_frame_rate_fair`` counts *steps* - what the shared gate answered
- on ten templates at two rates. That is the right thing to count for ten
templates at once, and it is not what a player has. A player has a course.

From C-1607 until C-1614 the racer covered 478.17 units in three real
seconds at 60Hz and 485.71 at 75, 120 and 144Hz. The check that existed
compared the three fast rates *with each other*, so the disagreement sat
in plain sight for seven cycles: the only screen that was wrong was the
only screen nothing was measured against. (The cause was hitstop - the
gate banked the held time and repaid it to whichever screen had spare
callbacks - and C-1614 fixed it.)

These tests read distance, at four rates, with 60Hz among them.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.racing import rate_probe

#: The rates MDN names as widely used, plus the one everything else is
#: written against.
RATES = (60.0, 75.0, 120.0, 144.0)

#: The lines a page needs for the four rates to agree, so each break
#: direction has a name. The first two are C-1614's halves; putting both
#: back reconstructs the page exactly as it stood from C-1607 to C-1614.
REAL_TIME_HOLD = "const asked=gap>0?(gap>=STEP-1?Math.max(1,gap/STEP):gap/STEP):1;"
DO_NOT_BANK = "TICK_FREEZE(gap>0?Math.min(held,gap):held);"
THE_GATE = "if (TICK_ACC < (dt >= TICK_MIN ? TICK_MIN : TICK_MS)) { return false }"

_READS: dict[tuple[str, float], dict] = {}


def _body() -> str:
    page = generate_game("レースゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    return found.group(1)


def _drive(body: str, hz: float, *, tag: str = "as built") -> dict:
    key = (tag, hz)
    if key not in _READS:
        run = subprocess.run(
            ["node", "-"], input=rate_probe(body, hz=hz),
            capture_output=True, text=True, timeout=300,
        )
        assert run.returncode == 0, run.stderr[:400]
        _READS[key] = json.loads(run.stdout.strip().splitlines()[-1])
    return _READS[key]


def _courses(body: str, *, tag: str = "as built") -> dict[float, float]:
    return {hz: _drive(body, hz, tag=tag)["dist"] for hz in RATES}


# --- the reading has to mean what it says ---------------------------


@pytest.mark.parametrize("hz", RATES)
def test_every_rate_drives_three_real_seconds(hz: float) -> None:
    """Comparing four numbers is only worth anything if they were taken
    over the same span of real time."""

    got = _drive(_body(), hz)

    assert got["realMs"] == 3000
    assert got["frames"] == round(hz * 3)


# --- the course ------------------------------------------------------


def test_four_refresh_rates_run_exactly_the_same_course() -> None:
    """Not "within a few percent": the same number."""

    seen = _courses(_body())

    assert min(seen.values()) > 0, "the racer did not move"
    assert len(set(seen.values())) == 1, f"the refresh rate picks the course: {seen}"


def test_the_same_course_took_the_same_number_of_steps() -> None:
    body = _body()
    steps = {hz: _drive(body, hz)["advanced"] for hz in RATES}

    assert len(set(steps.values())) == 1, steps


def test_the_picture_still_belongs_to_the_screen() -> None:
    """Making every screen equal by drawing 60 times a second would be the
    other half of the defect, not the fix."""

    body = _body()
    slow, fast = _drive(body, 60.0)["paints"], _drive(body, 144.0)["paints"]

    assert slow > 0
    assert fast / slow >= (144 / 60) * 0.9, f"{slow} at 60Hz vs {fast} at 144Hz"


# --- and what it is for ----------------------------------------------


def test_the_seven_cycles_of_blindness_reconstructed() -> None:
    """The break this measurement exists for, and the blindness it ends.

    Both of C-1614's halves put back is the page exactly as it stood from
    C-1607 onwards. It reads 478.17 at 60Hz and 485.71 at 75, 120 and
    144Hz - so **the fast three still agree perfectly with each other**,
    and the check that existed then compared only those three. It passed,
    every cycle, on a page where one screen in four ran a different
    course. Only bringing 60Hz into the comparison catches it, which is
    the whole of why this metric exists.
    """

    body = _body()
    assert REAL_TIME_HOLD in body and DO_NOT_BANK in body
    as_it_was = body.replace(REAL_TIME_HOLD, "const asked=1;").replace(DO_NOT_BANK, "")
    broken = _courses(as_it_was, tag="pre-C-1614")

    fast = {broken[hz] for hz in (75.0, 120.0, 144.0)}
    assert fast == {485.71}, f"the fast three agreed then, and must here: {broken}"
    assert broken[60.0] == 478.17, f"60Hz was the odd one out: {broken}"


def test_without_the_gate_every_screen_runs_a_different_course() -> None:
    """The coarser break, for completeness: no gate at all and the course
    is simply the refresh rate."""

    body = _body()
    assert THE_GATE in body
    broken = _courses(body.replace(THE_GATE, ""), tag="ungated")

    assert len(set(broken.values())) == len(RATES), broken
    # Not twice as far - the racer has a top speed, so the course
    # saturates - but strictly further on every faster screen.
    assert sorted(broken.values()) == [broken[hz] for hz in RATES], broken
