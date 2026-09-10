"""C-1614: the frame-rate judge was tolerating ±12 steps, and the whole of
that slack was hitstop.

``creation_frame_rate_fair`` asks whether two real seconds buy the same
amount of world on a 60Hz and a 120Hz screen. They did not: duel lost 5
steps on the 60Hz side, catch 6, racing 3. Hitstop - the brief freeze that
gives a hit its 手応え (§1) - was unfair in two separate ways, and only
fixing both closes the gap:

1. The hold was counted in *callbacks*, so a 7-frame hold lasted 117ms on a
   60Hz screen and 58ms on a 120Hz one. The hit landed softer on the better
   screen.
2. The time the world stood still was banked by the gate, which cannot tell
   a deliberate hold from a stalled tab. It hands that time back one step
   per callback - and a 120Hz screen has spare callbacks to collect it with
   while a 60Hz screen does not. ``TICK_FREEZE`` is how the holder says
   "charge this to nobody".

Measured on the real pages, deterministically, over two real seconds: how
many more steps of world the 120Hz screen bought than the 60Hz one.

===================  =====  =====  ======
fix applied          duel   catch  racing
===================  =====  =====  ======
neither (before)     +5     +6     +3
(1) only             +4     +6     +3
(2) only             +3     +5     +2
both                  0      0      0
===================  =====  =====  ======

Each half alone leaves the number outside the ±2 the judge now allows,
which is why both are here. The same run over three seconds closed a gap
nobody had looked at: the racer covered 478.17 at 60Hz and 485.71 at 75,
120 and 144Hz, and now covers 478.17 at all four.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.animation import PREAMBLE as ANIMATION_PREAMBLE
from sidra_ai.creation.animation import tick_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.juice import JUICE_PREAMBLE

#: The three templates that actually hitstop while being played by the
#: probe. The other seven never freeze, so they read 120/120 either way and
#: would pass a broken hold without noticing.
HITSTOPPERS = {
    "duel": "光線で撃ち合う対戦ゲームを作って",
    "catch": "フルーツキャッチを作って",
    "racing": "レースゲームを作って",
}

#: The two lines this item added, as they appear in a generated page. Used
#: to put each half of the fix back the way it was.
REAL_TIME_HOLD = "const asked=gap>0?(gap>=STEP-1?Math.max(1,gap/STEP):gap/STEP):1;"
DO_NOT_BANK = "TICK_FREEZE(gap>0?Math.min(held,gap):held);"

#: A hand-turned loop that holds the world once and counts what the hold
#: cost, in a page built from the two preambles and nothing else.
HOLD_HARNESS = """
let queued = null, MS = 0;
globalThis.matchMedia = () => ({ matches: false });
globalThis.document = { getElementById: () => null };
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
ANIMATION_PLACEHOLDER
JUICE_PLACEHOLDER
const MSPF = 1000 / RATE_INPUT;
let ran = 0;
const raf = requestAnimationFrame;
function loop(t){ ran++; raf(loop) }
raf(loop);
function step(){ const fn = queued; queued = null; MS += MSPF; fn(MS) }
for (let i = 0; i < 10; i++) { step() }
hitstop(FRAMES_INPUT);
const at = MS, was = ran;
let callbacks = 0;
while (ran === was && callbacks++ < 2000) { step() }
/* The callback that ran the world again is not part of the hold. */
console.log(JSON.stringify({
  heldMs: MS - at - MSPF, heldCallbacks: callbacks - 1 }));
"""


def _node(source: str) -> dict:
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=180
    )
    assert run.returncode == 0, run.stderr.strip()[:300]
    return json.loads(run.stdout.strip().splitlines()[-1])


def _hold(*, hz: float, frames: int = 7) -> dict:
    return _node(
        HOLD_HARNESS.replace("ANIMATION_PLACEHOLDER", ANIMATION_PREAMBLE)
        .replace("JUICE_PLACEHOLDER", JUICE_PREAMBLE)
        .replace("RATE_INPUT", repr(float(hz)))
        .replace("FRAMES_INPUT", str(frames))
    )


def _body(request: str) -> str:
    page = generate_game(request).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None, request
    return found.group(1)


def _steps(body: str, hz: float) -> int:
    return _node(tick_probe(body, hz=hz))["steps"]


def _spread(body: str) -> int:
    """How much more world two real seconds buy at 120Hz than at 60Hz."""

    return _steps(body, 120.0) - _steps(body, 60.0)


# --- the hold itself ------------------------------------------------


def test_a_hold_lasts_the_same_time_whatever_the_screen_does() -> None:
    """§1's 手応え is a duration. Counting callbacks made it a duration on
    one screen and half of it on another."""

    slow, fast = _hold(hz=60.0), _hold(hz=120.0)

    assert slow["heldCallbacks"] == 7, slow
    assert fast["heldCallbacks"] == 14, fast
    assert abs(slow["heldMs"] - fast["heldMs"]) < 1.0, (slow, fast)


def test_the_hold_ends_even_when_the_clock_never_moves() -> None:
    """The fallback that keeps this safe. A page whose timestamps stand
    still - a probe stubbing ``performance.now`` to a constant - must still
    come out of the hold, or it freezes for good. There the hold drains a
    whole frame per callback, exactly as it always did."""

    source = (
        HOLD_HARNESS.replace("ANIMATION_PLACEHOLDER", ANIMATION_PREAMBLE)
        .replace("JUICE_PLACEHOLDER", JUICE_PREAMBLE)
        .replace("RATE_INPUT", "0.0")  # MSPF is Infinity; MS never advances
        .replace("FRAMES_INPUT", "7")
        .replace("MS += MSPF", "MS += 0")
    )

    assert _node(source)["heldCallbacks"] == 7


# --- and the time it took -------------------------------------------


def test_the_gate_does_not_hand_back_time_the_world_was_held_for() -> None:
    """``TICK_FREEZE`` against no ``TICK_FREEZE``, on the gate alone.

    A hundred milliseconds pass with nobody asking. Told nothing, the gate
    banks them (to ``TICK_CAP``) and pays them out afterwards; told that the
    world was held, it charges the time to nobody and the run that follows
    is the run that would have followed no hold at all.
    """

    harness = """
ANIMATION_PLACEHOLDER
let steps = 0, now = 0;
for (let i = 0; i < 20; i++) { now += 8.0; if (TICK(now)) { steps++ } }
const settled = steps;
now += 100.0;               /* the world was held here */
FREEZE_PLACEHOLDER
for (let i = 0; i < 20; i++) { now += 8.0; if (TICK(now)) { steps++ } }
console.log(JSON.stringify({ settled: settled, after: steps - settled }));
"""
    base = harness.replace("ANIMATION_PLACEHOLDER", ANIMATION_PREAMBLE)
    silent = _node(base.replace("FREEZE_PLACEHOLDER", ""))
    told = _node(base.replace("FREEZE_PLACEHOLDER", "TICK_FREEZE(100.0);"))

    # Twenty callbacks of 8ms are 160ms of real time, which is nine whole
    # steps of world. (The first stretch reads 10: the gate's very first
    # call has no previous timestamp to measure from and always passes.)
    assert told["after"] == 9, told
    assert silent["after"] > told["after"], (silent, told)


# --- what that buys, on the real pages ------------------------------


@pytest.mark.parametrize("template", sorted(HITSTOPPERS))
def test_two_real_seconds_buy_the_same_world_on_either_screen(template: str) -> None:
    """The item's number, at its new tolerance."""

    assert abs(_spread(_body(HITSTOPPERS[template]))) <= 2


@pytest.mark.parametrize("template", sorted(HITSTOPPERS))
def test_counting_the_hold_in_callbacks_again_reopens_the_gap(template: str) -> None:
    """Break direction 1. Without this the real-time hold could be deleted
    and every check above would still pass."""

    body = _body(HITSTOPPERS[template])
    assert REAL_TIME_HOLD in body
    broken = body.replace(REAL_TIME_HOLD, "const asked=1;")

    assert _spread(body) == 0, "the fixed page must be exact, or this proves nothing"
    assert abs(_spread(broken)) > 0, template


def test_letting_the_gate_bank_the_held_time_reopens_the_gap() -> None:
    """Break direction 2, on the template it costs the most.

    catch loses 6 steps at 60Hz with the held time banked - three times the
    tolerance - which is what says ``TICK_FREEZE`` is load-bearing rather
    than decorative.
    """

    body = _body(HITSTOPPERS["catch"])
    assert DO_NOT_BANK in body
    broken = body.replace(DO_NOT_BANK, "")

    assert abs(_spread(broken)) > 2
