"""Does a flash last the same real time on a fast screen as on a slow one?

§6 定量 measured the owner's episode frame by frame and found a flash at
half brightness by a median of 0.20s. The note that recorded it checked
SIDRA's own value once, wrote "既存値とほぼ一致（変更不要）", and nothing
has held the number since. `creation_flash_cap` does run the real page at
60/120/144Hz, but it counts *onsets* - it asks how often the screen
flashes, never how long it stays bright - so a veil that vanishes in two
frames and a veil that hangs for three seconds both score full marks.

The defect this found (C-1892) was not a drifted constant. It was where
the constant was spent: `flash-=0.05` lived inside `draw()`, and `draw()`
runs once per refresh even on the frames the fixed-step `TICK` skips. The
simulation was on the clock and the juice was on the frame count, so the
flash got shorter as the screen got faster - 267ms at 60Hz, 133ms at
120Hz, 111ms at 144Hz, on the refresh rates §26 事実 1 calls ordinary.

What is measured here is the drawn veil, not the variable: a recording
context watches `globalAlpha` at the moment the page fills the whole
canvas, and the half-life is the real milliseconds from the peak to half
of it. Reading `flash` would have been the ledger again (C-1640) - the
page paints `0.5*ease(flash)`, so the variable's half-life and the
screen's are not the same number.

Three directions, because each catches a different way of passing:

  (a) the rates agree - every screen's half-life sits within TOLERANCE of
      the 60Hz one, which is the reading §6's check was made against;
  (b) the 60Hz reading stays inside a sane band - otherwise "fade at the
      same rate everywhere" is satisfied by a veil that never leaves;
  (c) the veil is actually painted - a peak alpha above a floor, so
      deleting the effect cannot pass a test about its length;
  (d) the table names every veil the product paints - otherwise the
      cheapest way to a full score is to stop looking at a page (the
      discipline C-1887 and C-1888 were written under).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.duel import KEY_EVENT_JS

#: The screens the callbacks come from. 60 is the one the value was
#: chosen on; 120 and 144 are the ones §26 事実 1 calls ordinary.
RATES: tuple[int, ...] = (60, 120, 144)

#: How far a screen's half-life may sit from the 60Hz reading. The
#: measurement is quantised by the callback interval itself (a 60Hz run
#: can only answer in 16.7ms steps), so this cannot be tight; it is far
#: below the 2.4x the frame-counted decay produced.
TOLERANCE = 0.35

#: The band the 60Hz reading itself must sit in, in milliseconds. §6's
#: film measured 0.20s; the page draws `k*ease(flash)`, so the veil the
#: eye sees outlasts the variable and the band is written around what the
#: screen shows rather than around the constant.
FLOOR_MS, CEIL_MS = 120.0, 450.0

#: A veil dimmer than this is not a flash. Without it, (a) and (b) are
#: both satisfiable by removing the effect.
PEAK_FLOOR = 0.15

#: The pages that paint a full-canvas veil, and the request that makes
#: each one. Every other template's hit reads as smoke, shake or a
#: recoloured body rather than a veil over the whole frame.
FLASH_PAGES: dict[str, str] = {
    "duel": "ビームで撃ち合うゲームを作って",
    "fishing": "魚釣りゲームを作って",
}

_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
/* The drawn veil. A full-canvas fillRect under a partial alpha is the
   flash; `globalAlpha` is followed across save/restore because a page is
   allowed to set it inside one. */
let _vAlpha = 1, _vVeil = 0; const _vStack = [];
const _vRec = new Proxy(function(){}, {
  get: (t, k) => {
    if (k === 'globalAlpha') return _vAlpha;
    if (k === 'save') return () => { _vStack.push(_vAlpha) };
    if (k === 'restore') return () => { _vAlpha = _vStack.length ? _vStack.pop() : 1 };
    if (k === 'fillRect') return (x, y, w, h) => {
      if (x === 0 && y === 0 && w === 720 && h === 320 && _vAlpha < 1 && _vAlpha > _vVeil) {
        _vVeil = _vAlpha } };
    if (k === Symbol.toPrimitive) return () => 0;
    return nothing },
  set: (t, k, v) => { if (k === 'globalAlpha') { _vAlpha = v } return true },
  apply: () => nothing });
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => _vRec }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
const STEP = STEP_MS_PLACEHOLDER;
function _vStepFrame(){ if (!queued) return false;
  const fn = queued; queued = null; _vVeil = 0; NOW += STEP; fn(NOW); return true }
function _vDown(){ (handlers.keydown||[]).forEach(fn => fn(probeKey(' '))) }
function _vUp(){ (handlers.keyup||[]).forEach(fn => fn(probeKey(' '))) }
_vDown(); _vUp(); for (let i = 0; i < 5; i++) _vStepFrame();
SETUP_PLACEHOLDER
/* Mash until a veil appears, then stop touching the page and follow that
   one veil down. A second onset while it falls restarts the reading, so
   the number is always one flash rather than an overlap of two. */
const _vLimit = Math.round(30000 / STEP);
let _vPeak = 0, _vT0 = 0, _vHalf = null, _vSeen = 0, _vHold = 0;
for (let i = 0; i < _vLimit && _vHalf === null; i++) {
  if (_vPeak === 0) { if (i % 12 < 8) { _vDown() } else if (i % 12 === 8) { _vUp() } }
  KEEPALIVE_PLACEHOLDER
  if (!_vStepFrame()) break;
  if (_vVeil > _vPeak + 0.02 && _vVeil > _vHold) {
    /* an onset: brighter than anything the fall had reached */
    _vPeak = _vVeil; _vT0 = NOW; _vSeen++; _vHold = 0 }
  else if (_vPeak > 0) {
    _vHold = _vVeil;
    if (_vVeil > 0 && _vVeil <= _vPeak / 2) { _vHalf = NOW - _vT0 } }
}
console.log(JSON.stringify({ halfMs: _vHalf, peak: _vPeak, onsets: _vSeen, step: STEP }));
"""

#: duel: match point is the fastest act and the barrage never ends early.
#: fishing needs nothing placed - a cast lands on its own.
_SETUP = {"duel": "e.hp = 1;", "fishing": ""}
#: Which template each creation module's veil belongs to. `games.py` holds
#: several small games and the veil in it is the fishing catch.
_MODULE_TEMPLATE = {"duel": "duel", "games": "fishing"}
#: The player must survive long enough to watch one veil fall.
_KEEPALIVE = {"duel": "p.hp = 3;", "fishing": ""}


@dataclass(frozen=True)
class FlashFadeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    halves: tuple[str, ...] = ()


def build_probe(script: str, *, template: str, hz: float) -> str:
    """The page's own script, wrapped so one veil can be timed."""

    return (
        _PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("STEP_MS_PLACEHOLDER", repr(1000.0 / float(hz)))
        .replace("SETUP_PLACEHOLDER", _SETUP[template])
        .replace("KEEPALIVE_PLACEHOLDER", _KEEPALIVE[template])
    )


def _run(job: tuple[str, int, str]) -> tuple[str, int, dict | str]:
    template, hz, script = job
    try:
        run = subprocess.run(
            ["node", "-"],
            input=build_probe(script, template=template, hz=hz),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return template, hz, f"probe unavailable ({type(exc).__name__})"
    if run.returncode != 0:
        return template, hz, run.stderr.strip()[:80] or "node failed"
    try:
        return template, hz, json.loads(run.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return template, hz, "probe printed nothing readable"


def veil_modules() -> set[str]:
    """Creation modules that fade a full-canvas veil, read from the source.

    This is the one place the source is read rather than the page, and it
    is read for a single purpose: to notice a veil that FLASH_PAGES does
    not name. The page itself still answers every question about length.
    """

    here = Path(__file__).resolve().parents[1] / "creation"
    return {
        path.stem
        for path in sorted(here.glob("*.py"))
        if "FLASH_FADE" in path.read_text(encoding="utf-8")
    }


def evaluate_flash_fades_in_real_time() -> FlashFadeResult:
    from sidra_ai.creation.games import generate_game

    jobs: list[tuple[str, int, str]] = []
    failures: list[str] = []
    for template, request in FLASH_PAGES.items():
        page = generate_game(request).html
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        if script is None:
            failures.append(f"{template}: no script on the page")
            continue
        for hz in RATES:
            jobs.append((template, hz, script.group(1)))

    readings: dict[tuple[str, int], dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for template, hz, out in pool.map(_run, jobs):
            if isinstance(out, str):
                failures.append(f"{template}@{hz}Hz: {out}")
            else:
                readings[(template, hz)] = out

    checks = 0
    halves: list[str] = []
    for template in FLASH_PAGES:
        got = {hz: readings[(template, hz)] for hz in RATES if (template, hz) in readings}
        if len(got) != len(RATES):
            continue
        missing = [hz for hz in RATES if got[hz].get("halfMs") is None]
        if missing:
            failures.append(
                f"{template}: no veil fell to half at "
                + "/".join(f"{hz}Hz" for hz in missing)
            )
            continue

        # (c) the effect is there to be timed
        peak = min(float(got[hz]["peak"]) for hz in RATES)
        if peak < PEAK_FLOOR:
            failures.append(f"{template}: the veil is barely painted (peak {peak:.2f})")
        else:
            checks += 1

        base = float(got[RATES[0]]["halfMs"])
        # (b) the anchor is a flash, not a curtain
        if not FLOOR_MS <= base <= CEIL_MS:
            failures.append(
                f"{template}: {RATES[0]}Hz half-life {base:.0f}ms is outside "
                f"{FLOOR_MS:.0f}-{CEIL_MS:.0f}ms"
            )
        else:
            checks += 1

        # (a) every screen agrees with it
        for hz in RATES[1:]:
            ms = float(got[hz]["halfMs"])
            # Signed, because the direction is the finding: a frame-counted
            # decay makes the flash SHORTER on a faster screen, and an
            # absolute value would have reported that as a rise.
            drift = (ms - base) / base if base else -1.0
            if abs(drift) > TOLERANCE:
                failures.append(
                    f"{template}: {hz}Hz half-life {ms:.0f}ms vs {base:.0f}ms "
                    f"at {RATES[0]}Hz ({drift:+.0%})"
                )
            else:
                checks += 1
        halves.append(
            f"{template}=" + "/".join(f"{hz}Hz {got[hz]['halfMs']:.0f}ms" for hz in RATES)
        )

    # (d) every veil the product paints is a veil this table times
    for module in sorted(veil_modules()):
        named = _MODULE_TEMPLATE.get(module)
        if named is None:
            failures.append(f"{module}.py fades a veil no template here names")
        elif named not in FLASH_PAGES:
            failures.append(f"{module}.py's veil ({named}) is not in FLASH_PAGES")
        else:
            checks += 1

    total = checks + len(failures)
    return FlashFadeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
        halves=tuple(halves),
    )
