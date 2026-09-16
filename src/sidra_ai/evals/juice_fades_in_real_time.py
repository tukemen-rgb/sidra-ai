"""Does the juice last the same real time on a fast screen as on a slow one?

C-1892 found the flash decaying once per callback rather than once per
unit of time, so it grew shorter as the screen grew faster. That fix
touched two templates' own code. This is the same defect one layer down,
in the shared juice every template goes through: `SHAKE*=0.78`,
`p.life-=0.045` and `p.life-=1/POP_LIFE` all lived inside the module's
`requestAnimationFrame` wrapper, spending exactly one frame's worth per
callback whatever the callback meant.

Measured before the fix, on the camera kick §1 names (Vlambeer's rule is
that the shake decays fast, and "fast" is a duration): half of a 9px kick
was gone after 50ms at 60Hz, 25ms at 120Hz and 20.8ms at 144Hz.

The judge that was already here could not see it. `creation_shake_settles_fast`
counts frames and divides by 60 to print seconds, so it reports the same
number at every refresh rate by construction - a frame-counted ruler
measuring a frame-counted effect. It is left alone: at 60Hz its numbers
are true and its other two directions (not a flicker, comes to rest) are
worth keeping. This judge supplies the axis it cannot have.

Both halves of the pair are read, because they decay by different
arithmetic - the shake multiplies, the particles subtract - and a fix
that only reached one of them should not be able to pass.

Three directions:

  (a) the rates agree with the 60Hz reading, which is the screen every
      one of these constants was chosen on;
  (b) that 60Hz reading is itself in a sane band, so "the same everywhere"
      cannot be satisfied by an effect that never leaves or never shows;
  (c) the effect is really there - a kick that never reaches the camera
      and a burst that pushes no particles are their own defect, and
      neither may buy a pass on a question about duration.
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.duel import KEY_EVENT_JS

#: The screens. 60 is where the constants come from; §26 事実 1 calls
#: 120 and 144 ordinary.
RATES: tuple[int, ...] = (60, 120, 144)

#: How far a rate may sit from the 60Hz reading. The measurement is
#: quantised by the callback interval itself, so this cannot be tight; the
#: defect it replaces was a factor of 2.4.
TOLERANCE = 0.25

#: Sane bands in milliseconds for the 60Hz readings, so an effect that
#: never fades cannot pass (a) by fading nowhere at every rate.
SHAKE_BAND = (20.0, 200.0)
PARTICLE_BAND = (120.0, 1500.0)

#: The page the readings are taken on. puzzle looked like the quiet
#: choice - a board that sits still until tapped - but it holds the frame
#: while it settles, and a held frame runs no steppers at all, so every
#: window opened on it was part fade and part hold. duel keeps its hold
#: for the moment a blow lands, which is a place the probe can wait out:
#: it settles first, and abandons any reading a hold walked into.
QUIET_REQUEST = "ビームで撃ち合うゲームを作って"

_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t,k)=>(k===Symbol.toPrimitive?()=>0:nothing), apply:()=>nothing, set:()=>true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = (type, fn) => { (handlers[type]=handlers[type]||[]).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width:720, height:320, style:{}, addEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:720,height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
const STEP = STEP_MS_PLACEHOLDER;
function _jFrame(){ if(!queued) return false; const fn=queued; queued=null; NOW+=STEP; fn(NOW); return true }
for (let i=0;i<8;i++) _jFrame();
/* Wait out any hold before starting. A held frame is held on purpose -
   the wrapper skips every stepper while hitstop is running - so real time
   spent inside a hold is not time the shake was given, and counting it
   would put the refresh rate straight back into the answer. C-1435 drew
   the same line for the attract demo's motion bar. */
function _jSettled(){ for(let i=0;i<600;i++){ if(hitstopFrames()<=0) return true;
    if(!_jFrame()) return false } return hitstopFrames()<=0 }
_jSettled();
/* The camera kick, through the page's own beat. */
shake(9);
const _jPeak = shakeAmount(); const _jT0 = NOW;
/* Only the time the page did not hold itself. A held callback runs no
   stepper at all, so that time was never offered to the fade; charging it
   would put the refresh rate back into the answer through the back door
   (C-1435 drew this line for the attract demo's motion bar). */
let _jHalf = null, _jSpent = 0, _jHeldMs = 0;
for (let i=0;i<6000;i++){ if(!_jFrame()) break;
  if (hitstopFrames() > 0) { _jHeldMs += STEP; continue }
  _jSpent += STEP;
  if (shakeAmount() <= _jPeak/2) { _jHalf = _jSpent; break } }
/* Then one burst, on a board that makes none of its own. */
_jSettled();
const _jBase = particleCount();
burst(100,100,12,'CYAN_TOKEN');
const _jBurst = particleCount() - _jBase; const _jT1 = NOW;
let _jGone = null, _jSpent2 = 0, _jHeldMs2 = 0;
for (let i=0;i<6000;i++){ if(!_jFrame()) break;
  if (hitstopFrames() > 0) { _jHeldMs2 += STEP; continue }
  _jSpent2 += STEP;
  if (particleCount() <= _jBase) { _jGone = _jSpent2; break } }
console.log(JSON.stringify({ step: STEP, peak: _jPeak, halfMs: _jHalf,
  burst: _jBurst, particleMs: _jGone,
  heldMs: _jHeldMs + _jHeldMs2, spentMs: _jSpent + _jSpent2 }));
"""


@dataclass(frozen=True)
class JuiceFadeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def build_probe(script: str, *, hz: float) -> str:
    return _PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "STEP_MS_PLACEHOLDER", repr(1000.0 / float(hz))
    )


def _run(job: tuple[int, str]) -> tuple[int, dict | str]:
    hz, script = job
    try:
        run = subprocess.run(
            ["node", "-"], input=build_probe(script, hz=hz),
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return hz, f"probe unavailable ({type(exc).__name__})"
    if run.returncode != 0:
        return hz, run.stderr.strip()[:80] or "node failed"
    try:
        return hz, json.loads(run.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return hz, "probe printed nothing readable"


def evaluate_juice_fades_in_real_time() -> JuiceFadeResult:
    from sidra_ai.creation.games import generate_game

    page = generate_game(QUIET_REQUEST).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    if script is None:
        return JuiceFadeResult(False, 0, 1, ("no script on the page",))

    failures: list[str] = []
    got: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for hz, out in pool.map(_run, [(hz, script.group(1)) for hz in RATES]):
            if isinstance(out, str):
                failures.append(f"{hz}Hz: {out}")
            else:
                got[hz] = out

    checks = 0
    readings: list[str] = []
    # The question is about the spread of screens, so measuring fewer of
    # them is not a cheaper way to the same answer: with RATES cut to
    # (60,) every comparison below simply stops happening and the sheet
    # comes back clean. 60 is where the constants were chosen and §26
    # 事実 1 names 120 and 144 as ordinary.
    if 60 not in RATES or len([hz for hz in RATES if hz > 60]) < 2:
        failures.append(
            "the rates measured are " + "/".join(f"{hz}Hz" for hz in RATES)
            + " - 60 and at least two faster screens are the question (§26 事実 1)"
        )
    else:
        checks += 1

    if len(got) == len(RATES):
        # (c) both effects are actually there to be timed
        if min(float(got[hz]["peak"]) for hz in RATES) <= 0:
            failures.append("the kick never reached the camera")
        else:
            checks += 1
        if min(int(got[hz]["burst"]) for hz in RATES) <= 0:
            failures.append("the burst pushed no particles")
        else:
            checks += 1

        # The window has to be mostly fade, not mostly hold: skipping held
        # time is right, but a reading taken from a handful of unheld
        # callbacks scattered through a long hold is not worth trusting.
        starved = [
            hz for hz in RATES
            if float(got[hz].get("spentMs") or 0) <= float(got[hz].get("heldMs") or 0)
        ]
        if starved:
            failures.append(
                "the page spent more of the window held than running at "
                + "/".join(f"{hz}Hz" for hz in starved)
            )
        else:
            checks += 1

        for label, key, band in (
            ("揺れ", "halfMs", SHAKE_BAND),
            ("粒子", "particleMs", PARTICLE_BAND),
        ):
            missing = [hz for hz in RATES if got[hz].get(key) is None]
            if missing:
                failures.append(
                    f"{label}: never faded at " + "/".join(f"{hz}Hz" for hz in missing)
                )
                continue
            base = float(got[RATES[0]][key])
            # (b) the anchor is a fade, not a fixture
            if not band[0] <= base <= band[1]:
                failures.append(
                    f"{label}: {RATES[0]}Hz reading {base:.0f}ms is outside "
                    f"{band[0]:.0f}-{band[1]:.0f}ms"
                )
                continue
            # (a) and every screen agrees with it
            drifted = False
            for hz in RATES[1:]:
                ms = float(got[hz][key])
                drift = (ms - base) / base if base else -1.0
                if abs(drift) > TOLERANCE:
                    failures.append(
                        f"{label}: {hz}Hz {ms:.0f}ms vs {base:.0f}ms at "
                        f"{RATES[0]}Hz ({drift:+.0%})"
                    )
                    drifted = True
                else:
                    checks += 1
            if not drifted:
                readings.append(
                    f"{label}=" + "/".join(f"{hz}Hz {got[hz][key]:.0f}ms" for hz in RATES)
                )

    return JuiceFadeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
