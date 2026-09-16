"""Does a generated picture advance by time, or by whatever the screen runs?

C-1892 put the flash on the clock, C-1898 the shared juice. This is the
third surface and the one where the consequence is not speed. Both art
patterns took one step per callback: over two real seconds the orbit
phase reached 121 at 60Hz, 241 at 120 and 289 at 144, and flow - which
draws by accumulating trails - laid down 31,320 strokes against 75,168.
flow's picture is its history, so the same seed made a different artwork
depending on the monitor it happened to be opened on.

What is read is the picture. Two earlier measures were tried and thrown
away, and both were the same mistake: counting strokes says a fast screen
differs from a slow one when the path is identical, and reading the
page's own tally of time handed out passes a body that takes the argument
and ignores it - a sabotage that did exactly that scored full marks
before this was rewritten. The only thing that settles it is the drawn
geometry, so the probe records every coordinate the page paints and
compares the frame drawn after the same amount of real time.

Three directions:

  (a) every screen is given the same amount of time for the same amount
      of real time;
  (b) the piece really moved over that window, because a frozen picture
      would satisfy (a) perfectly;
  (c) the page's own tally of time handed out matches the real seconds
      that passed - a weaker statement than (a), reported because a clock
      that stops is worth knowing about, and never a substitute for it.

And the table is checked against the product's own list of patterns, so a
pattern cannot be added without being measured (C-1887, C-1891, C-1894).
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

#: The screens. 60 is the one the constants were chosen on; §26 事実 1
#: calls 120 and 144 ordinary.
RATES: tuple[int, ...] = (60, 120, 144)

#: Real milliseconds each run is driven for.
WINDOW_MS = 2000.0

#: 60Hz frames' worth of time that window should buy, and how far a rate
#: may sit from the 60Hz reading. The defect was a factor of 2.4.
EXPECTED = WINDOW_MS * 60.0 / 1000.0
#: How far two frames may sit apart, as a share of the picture's own
#: scale. Floating-point accumulation over hundreds of callbacks never
#: lands on the same value twice, so this cannot be zero; the defect it
#: replaces moved the picture by more than its whole width.
TOLERANCE = 0.02
#: Below this, two frames are the same picture - used to catch a piece
#: that never moved rather than one that moved consistently.
FROZEN = 0.001

#: What "the same picture" means for each pattern, and why it differs.
#: orbits places its marks from a phase, so the same phase is the same
#: frame and the frames can be compared directly. flow integrates a noise
#: field one step at a time: a finer step traces the same curve more
#: accurately, so two rates legitimately end up at different points and
#: comparing frames would report a defect where there is none. What must
#: match there is how far the pen actually travelled.
MEASURE: dict[str, str] = {
    "orbits": "frame",
    "flow": "path",
}
MEASURE_WHY: dict[str, str] = {
    "orbits": "位相から位置を決めるので、同じ位相なら同じ絵",
    "flow": "流れ場を 1 歩ずつ積むので、刻みが細かいほど曲線を正確になぞる"
            "——**別の点に着くのが正しい**。揃うべきは「ペンが実際に進んだ距離」",
}
BAND = (EXPECTED * 0.8, EXPECTED * 1.2)

_PROBE = """
const nothing = new Proxy(function(){}, {
  get:(t,k)=>(k===Symbol.toPrimitive?()=>0:nothing), apply:()=>nothing, set:()=>true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.window = globalThis;
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return nothing };
/* Every coordinate the page paints, so the frame can be compared rather
   than counted. GEO is reset between frames by the driver below. */
let INK = 0, GEO = [], PATH = 0, PEN = null;
function _num(v){ return typeof v === 'number' && isFinite(v) ? Math.round(v * 100) / 100 : 0 }
const rec = new Proxy(function(){}, {
  get:(t,k)=>{
    if(k==='fillRect'||k==='strokeRect'||k==='rect')
      return (x,y,w,h)=>{ INK++; GEO.push(_num(x),_num(y),_num(w),_num(h)) };
    if(k==='moveTo')
      return (x,y)=>{ INK++; PEN=[x,y]; GEO.push(_num(x),_num(y)) };
    if(k==='lineTo')
      return (x,y)=>{ INK++;
        if(PEN){ const dx=x-PEN[0], dy=y-PEN[1];
          const d=Math.sqrt(dx*dx+dy*dy);
          /* a wrap across the canvas edge is not a stroke the eye follows */
          if(d < 100) PATH += d }
        PEN=[x,y]; GEO.push(_num(x),_num(y)) };
    if(k==='arc')
      return (x,y,r)=>{ INK++; GEO.push(_num(x),_num(y),_num(r)) };
    if(k==='stroke'||k==='fill') return ()=>{ INK++ };
    if(k===Symbol.toPrimitive) return ()=>0; return nothing },
  set:()=>true, apply:()=>nothing });
const _canvas = { width:720, height:420, style:{}, addEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:720,height:420}),
  getContext: () => rec };
globalThis.document = { getElementById: () => _canvas, querySelector: () => _canvas };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
const STEP = STEP_MS_PLACEHOLDER;
const N = Math.round(WINDOW_PLACEHOLDER / STEP);
const inkBefore = INK;
/* The picture as it stood one frame in, so "did it move at all" can be
   asked without a second run. */
let first = null;
for (let i=0;i<N && queued;i++){
  const fn=queued; queued=null; GEO=[]; NOW+=STEP; fn(NOW);
  if (i === 0) { first = GEO.slice() }
}
console.log(JSON.stringify({ step: STEP, callbacks: N, ink: INK - inkBefore,
  frame: GEO, first: first, path: PATH,
  advanced: (typeof artFacts === 'function' ? artFacts().advanced : null) }));
"""


@dataclass(frozen=True)
class ArtAdvanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def build_probe(script: str, *, hz: float) -> str:
    return (
        _PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("STEP_MS_PLACEHOLDER", repr(1000.0 / float(hz)))
        .replace("WINDOW_PLACEHOLDER", repr(WINDOW_MS))
    )


def _run(job: tuple[str, int, str]) -> tuple[str, int, dict | str]:
    pattern, hz, script = job
    try:
        run = subprocess.run(
            ["node", "-"], input=build_probe(script, hz=hz),
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return pattern, hz, f"probe unavailable ({type(exc).__name__})"
    if run.returncode != 0:
        return pattern, hz, run.stderr.strip()[:80] or "node failed"
    try:
        return pattern, hz, json.loads(run.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return pattern, hz, "probe printed nothing readable"


def evaluate_art_advances_in_real_time() -> ArtAdvanceResult:
    from sidra_ai.creation.art import _BODIES, generate_art

    failures: list[str] = []
    jobs: list[tuple[str, int, str]] = []
    for pattern in sorted(_BODIES):
        html = generate_art("抽象的な絵を作って", pattern=pattern).html
        script = re.search(r"<script>(.*?)</script>", html, re.S)
        if script is None:
            failures.append(f"{pattern}: no script on the page")
            continue
        for hz in RATES:
            jobs.append((pattern, hz, script.group(1)))

    got: dict[tuple[str, int], dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for pattern, hz, out in pool.map(_run, jobs):
            if isinstance(out, str):
                failures.append(f"{pattern}@{hz}Hz: {out}")
            else:
                got[(pattern, hz)] = out

    checks = 0
    readings: list[str] = []
    # Measuring fewer screens is not a cheaper way to the same answer:
    # with RATES cut to (60,) every comparison below stops happening and
    # the sheet comes back clean (C-1898 left this hole open once).
    if 60 not in RATES or len([hz for hz in RATES if hz > 60]) < 2:
        failures.append(
            "the rates measured are " + "/".join(f"{hz}Hz" for hz in RATES)
            + " - 60 and at least two faster screens are the question (§26 事実 1)"
        )
    else:
        checks += 1

    def _apart(a: list[float], b: list[float]) -> float:
        """How far two drawn frames sit apart, per coordinate.

        Same length is required first: a frame with a different number of
        marks is a different picture whatever its numbers say.
        """

        if len(a) != len(b) or not a:
            return float("inf")
        span = max(1.0, max(abs(v) for v in a))
        return max(abs(x - y) for x, y in zip(a, b)) / span

    for pattern in sorted(_BODIES):
        rows = {hz: got[(pattern, hz)] for hz in RATES if (pattern, hz) in got}
        if len(rows) != len(RATES):
            continue
        base_frame = rows[RATES[0]].get("frame") or []
        if not base_frame:
            failures.append(f"{pattern}: nothing was drawn")
            continue

        # (b) the picture moved over the window at all
        if _apart(base_frame, rows[RATES[0]].get("first") or []) <= FROZEN:
            failures.append(
                f"{pattern}: the frame after {WINDOW_MS / 1000:g}s is the "
                "frame after one callback - the piece never moved"
            )
        else:
            checks += 1

        # (c) the clock handed out roughly the seconds that passed
        handed = rows[RATES[0]].get("advanced")
        if handed is None or not BAND[0] <= float(handed) <= BAND[1]:
            failures.append(
                f"{pattern}: {RATES[0]}Hz was handed {handed} in "
                f"{WINDOW_MS / 1000:g}s, wanted about {EXPECTED:.0f}"
            )
        else:
            checks += 1

        # (a) and the same real time draws the same picture on every screen
        how = MEASURE.get(pattern)
        if how is None:
            failures.append(f"{pattern} has no measure named in MEASURE")
            continue

        def _off(hz: int) -> float:
            if how == "path":
                a = float(rows[RATES[0]].get("path") or 0.0)
                b = float(rows[hz].get("path") or 0.0)
                return float("inf") if a <= 0 else abs(b - a) / a
            return _apart(base_frame, rows[hz].get("frame") or [])

        drifted = False
        for hz in RATES[1:]:
            off = _off(hz)
            if off > TOLERANCE:
                failures.append(
                    f"{pattern}: after {WINDOW_MS / 1000:g}s the {hz}Hz "
                    f"{how} differs from the {RATES[0]}Hz one by {off:.0%}"
                )
                drifted = True
            else:
                checks += 1
        if not drifted:
            readings.append(
                f"{pattern}[{how}]="
                + "/".join(f"{hz}Hz {_off(hz):.1%}" for hz in RATES[1:])
            )

    for pattern in sorted(set(_BODIES) ^ set(MEASURE)):
        failures.append(f"{pattern}: named in MEASURE or in the product, not both")
    for pattern in sorted(MEASURE):
        if pattern not in MEASURE_WHY:
            failures.append(f"{pattern}: its measure has no written reason")
    if set(_BODIES) == set(MEASURE) == set(MEASURE_WHY):
        checks += 1

    return ArtAdvanceResult(
        passed=not failures and len(readings) == len(_BODIES),
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
