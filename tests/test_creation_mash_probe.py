"""Does mindless mashing win? The instrument that asks (C-1501).

The filed defect is that kaiju can be beaten unscathed on normal AND hard by
holding one key. Measuring it needs a driver that plays the cheapest possible
game - one key every frame, no steering - and a damage signal that works
without knowing any template's internals.

``sfx('hurt')`` is that signal: every template plays it when the player is
struck. Two things make it trustworthy, and both are tested here rather than
asserted in a comment.

**It proves itself every run.** The probe calls the shared damage sound once
at the end and reports whether its own counter moved. A run that says "never
struck" is only evidence if the instrument just demonstrated it can see a
strike; without that, a probe that silently failed to wrap ``sfx`` would
report every game as unpunishing and look like a finding.

**The prologue is not the fight.** kaiju roars with the same ``hurt`` sound on
its opening frame. Counting from frame zero would report the title card as
the player being hit - the exact false pass this measurement exists to avoid.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.games import _DIFFICULTY, generate_game
from sidra_ai.creation.round import mash_probe_source

HARD = sorted(key for key, bands in _DIFFICULTY.items() if "hard" in bands)


def drive(template: str, **kw):
    page = generate_game("難しいゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    done = subprocess.run(
        ["node", "-"],
        input=mash_probe_source(body, **kw),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def kaiju():
    return drive("kaiju")


# ------------------------------------------------ the instrument itself


def test_the_probe_proves_it_can_see_a_strike(kaiju: dict) -> None:
    """Without this, "never struck" and "never counted" are the same reading."""

    assert kaiju["selfCheck"] == 1


@pytest.mark.parametrize("template", HARD)
def test_every_template_reports_a_working_counter(template: str) -> None:
    assert drive(template)["selfCheck"] == 1


def test_the_opening_roar_is_not_counted_as_a_hit() -> None:
    """kaiju plays the damage sound on frame one. It is not damage.

    Driven both ways on the same page: with the count starting inside the
    fight (as the probe does) and with it starting at frame zero. The second
    reading has to be higher, or the exclusion is not doing anything and the
    default would be reporting a title card as a punished masher.
    """

    inside = drive("kaiju")["struck"]
    from_zero = drive("kaiju", warmup=0)["struck"]
    assert from_zero > inside
    assert inside == 0


# ------------------------------------------------------------ the driving


def test_holding_two_keys_drives_both(kaiju: dict) -> None:
    """A masher and a walker have to be separable on the same page.

    A fix that punished playing at all would be indistinguishable from one
    that punished standing still if only one input could be driven.
    """

    walked = drive("kaiju", hold=[" ", "ArrowLeft"])
    assert walked["selfCheck"] == 1
    assert walked != kaiju


def test_a_bare_string_hold_is_one_key(kaiju: dict) -> None:
    assert drive("kaiju", hold=" ") == kaiju


def test_the_run_reports_where_it_ended(kaiju: dict) -> None:
    """"Never hit" and "never finished" are different findings."""

    assert kaiju["endedAt"] is not None
    assert kaiju["ended"] or kaiju["done"]


# ----------------------------------------------------------- the finding


@pytest.mark.parametrize("template", HARD)
def test_the_measured_state_of_the_board_is_recorded(template: str) -> None:
    """The defect, pinned as it stands: on hard, mashing is never punished.

    This is a **regression test for a bug that is still open** - C-1501 is
    recorded, not fixed, because punishing a stationary player collides with
    the graze band that pays for standing beside danger (C-1419), and which
    of those kaiju's boss fight is for is a design call, not a constant to
    tune. When that is decided, this expectation is what has to change, and
    the number it guards is ``creation_mash_punished``.
    """

    assert drive(template)["struck"] == 0
