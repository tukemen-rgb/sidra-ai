"""The flash cap counts seconds, not callbacks (§15 事実 1 × §26, C-1708).

WCAG 2.3.1, as §15 records it, is written in seconds: no more than three
onsets in any one-second period. ``flashGate()`` enforced it over a
rolling sixty **frames**, and ``FLASH_FRAME`` advances once per rAF
callback - which §26 事実 1 says arrives once per refresh, on screens
that are routinely 120Hz or 144Hz. Sixty callbacks there is half a
second, so the gate passed six onsets a second.

Measured on the duel's mash fire at match-point tempo, before the fix:
three onsets in the worst real second at 60Hz and **four** at 120Hz and
144Hz. The judge did not see it because it, too, said "one second" and
counted frames at a hand-turned flat 16ms.

Both windows are kept. The clock is the rule; the frame window answers
when there is no usable clock, because a probe that stubs the timestamp
to a constant would otherwise hold its onsets forever and refuse every
flash for the rest of the page's life.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.duel import flash_probe
from sidra_ai.creation.games import generate_game

RATES = (60, 120, 144)
ALIVE = 5  # onsets over the fifteen-second run


@pytest.fixture(scope="module")
def script() -> str:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ビームで撃ち合うゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    return found.group(1)


@pytest.fixture(scope="module")
def screens(script: str) -> dict[int, dict]:
    seen = {}
    for hz in RATES:
        got = subprocess.run(
            ["node", "-"],
            input=flash_probe(script, hz=hz),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert got.returncode == 0, (hz, got.stderr[:400])
        seen[hz] = json.loads(got.stdout.strip().splitlines()[-1])
    return seen


@pytest.mark.parametrize("hz", RATES)
def test_no_real_second_holds_a_fourth_flash(screens: dict, hz: int) -> None:
    shot = screens[hz]
    assert shot["worstSecond"] <= 3, (hz, shot["worstSecond"], shot["onsets"])


@pytest.mark.parametrize("hz", RATES)
def test_the_cap_does_not_kill_the_flash(screens: dict, hz: int) -> None:
    """A gate that passes by removing the effect is a different defect."""

    assert screens[hz]["onsets"] >= ALIVE, (hz, screens[hz]["onsets"])


def test_the_fast_screens_really_were_faster(screens: dict) -> None:
    """Without this the parametrized cases above could all be the same
    60Hz run wearing three labels - the fault only appears when a second
    holds more callbacks."""

    for hz in RATES:
        shot = screens[hz]
        assert shot["ms"] == pytest.approx(15000, abs=200), (hz, shot["ms"])
        assert shot["frames"] == pytest.approx(15 * hz, rel=0.02), (hz, shot["frames"])
    assert screens[144]["frames"] > screens[120]["frames"] > screens[60]["frames"]


def test_a_clock_that_never_moves_does_not_stop_the_flash(script: str) -> None:
    """The frame window is not decoration. A page whose timestamps never
    move is a stub, not a slow screen - believing it would leave the
    one-second window frozen and refuse every flash after the third for
    the rest of the page's life."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    got = subprocess.run(
        ["node", "-"],
        input=flash_probe(script, hz=None),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert got.returncode == 0, got.stderr[:400]
    frozen = json.loads(got.stdout.strip().splitlines()[-1])
    assert frozen["ms"] == 0, frozen["ms"]
    assert frozen["onsets"] >= ALIVE, frozen["onsets"]
    assert frozen["worstWindow"] <= 3, frozen["worstWindow"]


def test_the_gate_carries_a_clock_at_all(script: str) -> None:
    """The frame window is still there as the fallback, so a page could
    satisfy every count above while the clock half was never wired in.
    Read the page's own report of which window it is using."""

    probe = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n, step){ for (let i = 0; i < n && queued; i++) {
  const fn = queued; queued = null; NOW += step; fn(NOW) } }
run(8, 8);
const moving = flashFacts();
/* A clock that never advances is a stub, not a screen. */
run(8, 0);
const stuck = flashFacts();
console.log(JSON.stringify({ moving: moving, stuck: stuck }));
"""
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    got = subprocess.run(
        ["node", "-"],
        input=probe.replace("SCRIPT_PLACEHOLDER", script),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert got.returncode == 0, got.stderr[:400]
    seen = json.loads(got.stdout.strip().splitlines()[-1])
    assert seen["moving"]["timed"] is True, seen["moving"]
    assert seen["moving"]["clock"] == pytest.approx(64, abs=1), seen["moving"]
    # The stub keeps the clock where it was; the gate stays timed because
    # it has already seen the clock move, and the frame window is what
    # protects a page whose timestamps never move at all.
    assert seen["stuck"]["clock"] == seen["moving"]["clock"], seen["stuck"]


def test_the_rule_is_written_in_the_unit_the_rule_uses(script: str) -> None:
    """The window that used to be spelled only in frames."""

    from sidra_ai.creation import juice

    assert "FLASH_CLOCK-t<1000" in juice.JUICE_PREAMBLE
    assert "FLASH_FRAME-t<60" in juice.JUICE_PREAMBLE  # the fallback stays
    assert "flashGate" in script and "FLASH_CLOCK" in script
