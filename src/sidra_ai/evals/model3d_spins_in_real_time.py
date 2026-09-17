"""Does the 3D preview turn by time, or by whatever the screen runs?

C-1892 put the game flash on the clock, C-1898 the shared juice, C-1900
the art. Those three closed every animated surface the loops had looked
at - and missed this one, because a 3D preview is neither a game nor a
picture. Its loop was a raw per-callback nudge:

    (function tick(){ angle += 0.012; render(angle);
                      requestAnimationFrame(tick); })();

`requestAnimationFrame` fires once per refresh, so over the same two real
seconds the model reached 1.452 rad on a 60Hz screen and 3.468 on a 144Hz
one - **2.39 times further**, with an entirely different frame on screen
at the same moment. §26 fact 1 calls 120 and 144 ordinary, so this is
most screens rather than an edge case.

What is read is the **drawn geometry**, not the page's own angle. C-1900
threw away two cheaper measures for reasons that apply here too: counting
callbacks says nothing about what was painted, and reading a variable the
page maintains passes an implementation that keeps the variable honest
while drawing something else.

The geometry is compared as the painted shape's **extent** rather than as
a raw vertex list. Two frames a thousandth of a turn apart can differ by
one face, because back-face culling flips a face sitting exactly on the
boundary, and comparing vertex lists calls that a different picture when
it is the same pose. The extent moves smoothly with the pose; the vertex
count rides along, so a shape that stops painting altogether cannot hide
behind an unchanged box (sabotage D6).

Three directions:

  (a) the same real time buys the same picture on every screen;
  (b) the model really turned over that window - a frozen preview would
      satisfy (a) perfectly;
  (c) and the 60Hz frame still lands where it always did, because a rate
      correction that also changes the speed everyone already sees is not
      a correction.

Frames are sampled at fixed marks of REAL time rather than at fixed
callback counts - a callback count is the very thing under measurement.
Four marks rather than one because a shape may legitimately paint nothing
at some angles: the terrain's faces are all turned away between roughly
1.0 and 2.0 rad, so a single sample could catch an empty frame and leave
nothing to compare. (That the terrain preview is blank for part of its
turn is a separate matter, recorded with C-1922 rather than fixed here.)

The table is the product's own ``_SHAPES`` registry, so a shape cannot be
added without being measured (C-1887, C-1891, C-1894).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

#: The screens. 60 is the one 0.012 was chosen on; §26 fact 1 calls 120
#: and 144 ordinary.
RATES: tuple[int, ...] = (60, 120, 144)

#: Real milliseconds each run is driven for.
WINDOW_MS = 2000.0

#: Where in the window the frames are compared, in real milliseconds.
MARKS: tuple[float, ...] = tuple(WINDOW_MS * f for f in (0.25, 0.5, 0.75, 1.0))

#: What the 60Hz run should still land on: 0.012 rad per 60Hz frame over
#: the window, plus the one the page draws synchronously when it starts -
#: the loop calls `tick()` itself before the first refresh and that frame
#: is a step. It was a step before this fix too, which is why the pre-fix
#: 60Hz reading was 1.452 rather than 1.440. Written out rather than read
#: back from the run, so a "fix" cannot quietly change the speed everyone
#: already sees and still call itself correct.
EXPECTED_60HZ = 0.012 * (WINDOW_MS * 60.0 / 1000.0 + 1)

#: How far two rates' frames may sit apart, in canvas pixels. Floating
#: point over hundreds of callbacks never lands twice on the same value;
#: the defect this replaces moved vertices by hundreds of pixels.
TOLERANCE_PX = 4.0

#: Below this the preview never moved at all.
FROZEN_PX = 1.0

_PROBE = """
const nothing = new Proxy(function(){}, {
  get:(t,k)=>(k===Symbol.toPrimitive?()=>0:nothing), apply:()=>nothing, set:()=>true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.window = globalThis;
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = () => {};
/* Every vertex the page paints, so the FRAME can be compared rather than
   the page's own bookkeeping. GEO is reset between frames by the driver. */
let GEO = [];
/* The painted shape's extent, rather than its raw vertex list. Two frames
   0.006 rad apart can differ by one face - back-face culling flips a face
   that sits exactly on the boundary - and comparing raw lists calls that a
   different picture when it is the same pose. The extent moves smoothly
   with the pose and does not jump when one face appears. (C-1900 threw out
   stroke counts for the same class of reason: a measure has to be
   insensitive to what legitimately differs and sensitive to what must
   not.) The vertex count rides along so a shape that stops painting
   entirely cannot hide behind an unchanged box. */
function box(g){
  if (!g.length) { return { n:0, b:null } }
  let x0=g[0],x1=g[0],y0=g[1],y1=g[1];
  for (let i=0;i<g.length;i+=2){
    if(g[i]<x0)x0=g[i]; if(g[i]>x1)x1=g[i];
    if(g[i+1]<y0)y0=g[i+1]; if(g[i+1]>y1)y1=g[i+1];
  }
  return { n:g.length, b:[_num(x0),_num(y0),_num(x1),_num(y1)] };
}
function _num(v){ return typeof v === 'number' && isFinite(v) ? Math.round(v*100)/100 : 0 }
const rec = new Proxy(function(){}, {
  get:(t,k)=>{
    if(k==='moveTo'||k==='lineTo') return (x,y)=>{ GEO.push(_num(x),_num(y)) };
    if(k===Symbol.toPrimitive) return ()=>0; return nothing },
  set:()=>true, apply:()=>nothing });
const _canvas = { width:640, height:480, style:{}, addEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:640,height:480}),
  getContext: () => rec };
globalThis.document = { getElementById: () => _canvas, querySelector: () => _canvas };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
const STEP = STEP_PLACEHOLDER;
const N = Math.round(WINDOW_PLACEHOLDER / STEP);
const MARKS = MARKS_PLACEHOLDER;
/* The frame to compare is the one whose callback index lands on the mark:
   NOW is built by repeated addition, so it drifts (sixty steps of 1000/60
   sum to 999.9999999999999, not 1000) and a plain `NOW >= mark` test made
   60Hz miss the 1000ms mark and sample the next frame instead - one frame
   of skew, on one rate only, which then looks like disagreement between
   screens rather than a sampling artifact. Indexing by the mark removes
   the drift from the comparison entirely. */
const WANT = MARKS.map((t) => Math.round(t / STEP));
const shots = [];
for (let i=1;i<=N && queued;i++){
  const fn=queued; queued=null; GEO=[]; NOW+=STEP; fn(NOW);
  if (WANT.indexOf(i) !== -1) { shots.push(box(GEO)) }
}
console.log(JSON.stringify({ step:STEP, callbacks:N, shots:shots,
  angle: (typeof angle !== 'undefined' ? angle : null) }));
"""


@dataclass(frozen=True)
class SpinResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def build_probe(script: str, *, hz: float) -> str:
    return (
        _PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("STEP_PLACEHOLDER", repr(1000.0 / float(hz)))
        .replace("WINDOW_PLACEHOLDER", repr(WINDOW_MS))
        .replace("MARKS_PLACEHOLDER", json.dumps(list(MARKS)))
    )


def _run(job: tuple[str, int, str]) -> tuple[str, int, dict | str]:
    shape, hz, script = job
    from sidra_ai.evals.scratch import scratch_dir

    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, dir=str(scratch_dir()), encoding="utf-8"
    ) as handle:
        handle.write(build_probe(script, hz=hz))
        path = handle.name
    try:
        done = subprocess.run(
            ["node", path], capture_output=True, text=True, timeout=120
        )
        if done.returncode != 0:
            return shape, hz, f"node exited {done.returncode}: {done.stderr[-200:]}"
        return shape, hz, json.loads(done.stdout.strip().splitlines()[-1])
    except Exception as err:  # a probe that cannot run is a failure, not a pass
        return shape, hz, f"{type(err).__name__}: {err}"
    finally:
        os.unlink(path)


#: How far two frames' vertex counts may differ, as a share of the larger.
#: A face flipping across the culling boundary is a handful of vertices; a
#: shape that stopped drawing is not.
COUNT_SLACK = 0.1


def _apart(a: dict, b: dict) -> float:
    """How far apart two sampled frames are, in canvas pixels.

    Both empty is the same picture - the terrain paints nothing while its
    faces are all turned away, and at the same pose on two screens it
    paints nothing twice. One empty and one not is infinite, as is a
    vertex count that moved by more than a face or two.
    """

    box_a, box_b = a.get("b"), b.get("b")
    if box_a is None and box_b is None:
        return 0.0
    if box_a is None or box_b is None:
        return float("inf")
    biggest = max(a.get("n") or 0, b.get("n") or 0, 1)
    if abs((a.get("n") or 0) - (b.get("n") or 0)) > biggest * COUNT_SLACK:
        return float("inf")
    return max(abs(x - y) for x, y in zip(box_a, box_b))


def evaluate_model3d_spins_in_real_time() -> SpinResult:
    from sidra_ai.creation.models3d import _SHAPES, generate_model3d

    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    shapes = tuple(sorted(_SHAPES))
    if not shapes:
        return SpinResult(False, 0, 1, ("the product lists no shapes at all",))
    if 60 not in RATES or not {120, 144} <= set(RATES):
        failures.append(
            "the rates measured must include 60 and the two §26 calls ordinary "
            f"(120, 144) - got {RATES}"
        )
    else:
        checks += 1

    jobs: list[tuple[str, int, str]] = []
    for shape in shapes:
        html = generate_model3d("3Dモデルを作って", shape=shape).preview_html
        found = re.search(r"<script>(.*?)</script>", html, re.S)
        if not found:
            failures.append(f"{shape}: the preview page carries no script")
            continue
        for hz in RATES:
            jobs.append((shape, hz, found.group(1)))

    runs: dict[tuple[str, int], dict | str] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for shape, hz, out in pool.map(_run, jobs):
            runs[(shape, hz)] = out

    for shape in shapes:
        base = runs.get((shape, 60))
        if isinstance(base, str) or base is None:
            failures.append(f"{shape}@60Hz: {base or 'did not run'}")
            continue
        shots = base.get("shots") or []

        # (b) it turned at all, measured across the sampled frames - a shape
        # that paints nothing at one angle has an empty frame there, so
        # comparing only the first and the last would read that as frozen.
        moved = max((_apart(shots[0], later) for later in shots[1:]), default=0.0)
        if moved < FROZEN_PX:
            failures.append(
                f"{shape}: the preview never turned - {moved:.2f}px across the "
                f"{len(shots)} sampled frames"
            )
            continue
        checks += 1

        # (c) 60Hz still lands where it always did
        angle = base.get("angle")
        if not isinstance(angle, (int, float)) or abs(angle - EXPECTED_60HZ) > 0.01:
            failures.append(
                f"{shape}@60Hz: turned {angle} rad, wanted {EXPECTED_60HZ:.3f} - "
                "the fix changed the speed everyone already sees"
            )
        else:
            checks += 1

        # (a) every screen buys the same picture for the same real time
        for hz in RATES:
            if hz == 60:
                continue
            other = runs.get((shape, hz))
            if isinstance(other, str) or other is None:
                failures.append(f"{shape}@{hz}Hz: {other or 'did not run'}")
                continue
            theirs = other.get("shots") or []
            if len(theirs) != len(shots):
                apart = float("inf")
            else:
                apart = max(
                    (_apart(a, b) for a, b in zip(shots, theirs)),
                    default=float("inf"),
                )
            if apart > TOLERANCE_PX:
                failures.append(
                    f"{shape}@{hz}Hz: {apart:.1f}px from the 60Hz frames at the "
                    f"same real times ({other.get('callbacks')} callbacks "
                    f"against {base.get('callbacks')})"
                )
            else:
                checks += 1
        readings.append(f"{shape} {angle:.3f} rad @60Hz")

    return SpinResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
