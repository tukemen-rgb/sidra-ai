"""Does mindless mashing win? The instrument that asks (C-1501, C-1623).

The filed defect is that kaiju can be beaten unscathed on normal AND hard by
holding one key. Measuring it needs a driver that plays the cheapest possible
game - one key every frame, no steering - and a punishment signal that works
without knowing any template's internals.

Both halves were wrong for as long as this existed, and ``creation_mash_punished``
reported 0 the whole time - not "nothing punishes a masher" but "nothing was
ever measured" (C-1623).

**The key has two halves and the pages do not agree which one they read.**
``mPress`` sent ``code: ' '`` for the space bar. No browser produces that code;
the real one is ``'Space'``. kaiju listens on ``e.key`` and was driven, while
shooter, duel, puzzle and fishing listen on ``e.code`` and were not - the
shooter fired 0 shots in 5400 frames of "mashing".

**The damage sound is not a verdict.** ``sfx('hurt')`` was the count. In the
shooter it plays when a FOE dies and stays silent when the ship does, so a run
that ended in the player's death came back as "unscathed"; in the duel it plays
for whichever fighter was hit. The count is the shared FAILURE BEAT now - the
signal ``roundLost()`` already reads - and the sound is still reported, because
it is worth seeing, never as the verdict.

**The buzzer rings the failure beat too.** ``roundTick`` fires it when the
round clock runs out, and every unattended run reaches the clock. Counting
that would report all ten templates as punishing a masher. Only beats that
land while the go is still being PLAYED count.

**It proves itself every run.** The probe rings the failure beat and the damage
sound once each at the end and reports whether its own counters moved. A run
that says "never beaten" is only evidence if the instrument just demonstrated
it can see a defeat.

**The prologue is not the fight.** kaiju roars with the ``hurt`` sound on its
opening frame. Counting from frame zero would report the title card as the
player being hit - the exact false pass this measurement exists to avoid.
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


def test_the_probe_proves_it_can_see_a_defeat(kaiju: dict) -> None:
    """The counter the verdict is actually read off (C-1623)."""

    assert kaiju["failCheck"] == 1


@pytest.mark.parametrize("template", HARD)
def test_every_template_reports_a_working_counter(template: str) -> None:
    got = drive(template)
    assert got["selfCheck"] == 1
    assert got["failCheck"] == 1


def test_the_proving_beat_is_not_counted_as_a_defeat() -> None:
    """The instrument rings the beat to prove it can hear one. A run that
    ended on its own terms - racing reaches its goal, so the round clock
    never rings - leaves the go open, and a careless order would let the
    proving ring land inside the count it exists to prove."""

    goaled = drive("racing")
    assert goaled["state"] == "goal"
    assert goaled["failCheck"] == 1
    assert goaled["beaten"] == 0


@pytest.mark.parametrize("template", ["adventure", "catch", "platformer"])
def test_the_buzzer_is_not_counted_as_punishment(template: str) -> None:
    """``roundTick`` rings the failure beat when the clock runs out, and an
    unattended go always reaches the clock. Counted, it would report every
    template as punishing a masher."""

    got = drive(template)
    assert got["reason"] == "time"
    assert got["fails"] >= 1, "the buzzer did not ring, so this proves nothing"
    assert got["beaten"] == 0


def test_the_damage_sound_is_not_the_verdict() -> None:
    """Why the count moved off ``sfx('hurt')`` (C-1623), measured rather
    than argued: the shooter plays it 55 times in a go it loses twice,
    because it is what a dying FOE sounds like."""

    got = drive("shooter")
    assert got["struck"] > got["beaten"] * 10, (
        f"struck {got['struck']} vs beaten {got['beaten']}"
    )


def test_the_opening_roar_is_not_counted_as_a_hit() -> None:
    """kaiju plays the damage sound on frame one. It is not damage.

    Driven both ways on the same page: with the count starting inside the
    fight (as the probe does) and with it starting at frame zero. The second
    reading has to be higher, or the exclusion is not doing anything and the
    default would be reporting a title card as a punished masher.
    """

    inside = drive("kaiju")
    from_zero = drive("kaiju", warmup=0)
    assert from_zero["struck"] > inside["struck"]
    assert inside["struck"] == 0
    # And the same run through the signal the verdict is read off: the roar
    # is not a failure beat at all, so this one never needed the exclusion.
    assert from_zero["beaten"] == 0


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


def test_the_driver_reaches_a_page_that_gates_on_the_code() -> None:
    """The half that was never reached (C-1623). The duel reads
    ``ev.code==='Space'`` and nothing else; if the code regressed to ``' '``
    it would sit through 5400 frames untouched and come back unbeaten."""

    assert drive("duel")["beaten"] > 0


def test_the_driver_still_reaches_a_page_that_gates_on_the_key() -> None:
    """And the half that always worked has to keep working: kaiju reads
    ``e.key===' '``, so a fix that sent only the code would break it."""

    assert drive("kaiju")["score"] > 0


def test_no_probe_in_this_module_sends_a_key_as_its_own_code() -> None:
    """The shape of the defect, caught at the source (C-1623).

    Nine places in ``round.py`` synthesise a keydown and seven of them
    already wrote ``code: k === ' ' ? 'Space' : k``. The two that did not
    are why this item exists, and the mistake is invisible from a passing
    run - the page simply does nothing.
    """

    import pathlib

    import sidra_ai.creation.round as module

    text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    bad = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"code:\s*(k|key)\s*[,}]", line)
    ]
    assert bad == [], f"a key sent as its own code: {bad}"


# ----------------------------------------------------------- the finding


#: Measured with the corrected instrument (C-1623). Two of ten.
PUNISHED = {"duel", "shooter"}


@pytest.mark.parametrize("template", HARD)
def test_the_measured_state_of_the_board_is_recorded(template: str) -> None:
    """The defect, pinned as it stands: on hard, eight of ten templates let
    a player who presses one key and never steers through untouched.

    This is a **regression test for a bug that is still open** - C-1501 is
    recorded, not fixed, because punishing a stationary player collides with
    the graze band that pays for standing beside danger (C-1419), and which
    of those kaiju's boss fight is for is a design call, not a constant to
    tune. When that is decided, this expectation is what has to change, and
    the number it guards is ``creation_mash_punished``.

    What changed in C-1623 is only that the reading is now taken with a
    driver the pages can hear and a signal that means what it says. The two
    that punish a masher were always punishing one; nobody could see it.
    """

    beaten = drive(template)["beaten"]
    assert (beaten > 0) is (template in PUNISHED), f"{template}: beaten {beaten}"


@pytest.mark.parametrize("template", ["kaiju", "racing"])
def test_two_of_them_are_not_merely_survived_but_won(template: str) -> None:
    """The worst of the eight, kept in front of whoever fixes them: on
    ``hard``, one key and no steering does not just come through alive - it
    reaches the winning screen. kaiju takes all three cycles, racing crosses
    its last line in about 39 seconds of a 60-second clock.
    """

    got = drive(template)
    assert got["beaten"] == 0
    assert got["state"] in {"won", "goal"}, got["state"]
    assert got["reason"] == "template", "the clock ended it, not the template"
