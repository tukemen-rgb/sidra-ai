"""How much a frame is allowed to draw (§32, C-1752).

§26 settled what a frame *is* - the refresh rate and the units time is
counted in - and nothing said how much work may go inside one. The
judges read every colour and every word this product paints and never
once asked how many calls it took.

RAIL puts the number at **10ms of the application's own work per frame**:
the 16ms a 60fps frame allows, less the ~6ms a browser spends rendering
it (web.dev, read 2026-09-13). That is a *time*, and time is exactly what
a recording context in node cannot measure - it can count calls, and how
many microseconds a call costs is the device's business.

So this module does not invent a threshold. It records what each template
draws today and refuses a change that quietly makes it much heavier. The
10ms stays in §32 as the thing a person reasons with when the ceiling is
reached; the ceiling itself only says "this grew".

Measured 2026-09-13, ten templates driven 2400 frames by an ignorant
masher, counting calls into the canvas context per frame. The spread is
twenty-fold - catch 21, adventure 530 - which is not a fault, but it was
nobody's knowledge before it was written down here.
"""

from __future__ import annotations

from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: Median calls into the canvas context per drawn frame, as measured.
FRAME_MEDIAN: dict[str, int] = {
    "catch": 21,
    "fishing": 33,
    "duel": 40,
    "kaiju": 55,
    "platformer": 119,
    "shooter": 147,
    "marble": 184,
    "puzzle": 284,
    "racing": 478,
    "adventure": 530,
}

#: How far above the measurement a template may drift before this is
#: worth a person's attention. A fifth: big enough that adding a detail
#: does not cry wolf, small enough that doubling the work cannot hide.
FRAME_SLACK = 1.2


#: The 95th percentile of the same ten runs, measured 2026-09-13 at the
#: 1200 frames the judge actually drives - not the 2400 of the §32 write-up.
#: A percentile is a property of its window, so the number has to come from
#: the window it will be checked in (kaiju, marble and puzzle all differ
#: between the two windows).
#:
#: §32's own reading of its table says this is the column to watch: the
#: templates whose peak runs far above their middle (fishing 33 -> 112,
#: shooter 147 -> 245) do three times the work at the climax, and that is
#: where §1's juice sits. A ratchet on the median alone cannot see a change
#: that only moves the spike - a few dozen loud frames out of 1200 leave the
#: median where it was.
FRAME_P95: dict[str, int] = {
    "catch": 36,
    "fishing": 112,
    "duel": 61,
    "kaiju": 91,
    "platformer": 121,
    "shooter": 245,
    "marble": 198,
    "puzzle": 317,
    "racing": 502,
    "adventure": 532,
}


def frame_ceiling(template: str) -> int:
    """The most this template may draw per frame before the judge objects."""

    return int(FRAME_MEDIAN[template] * FRAME_SLACK)


def frame_peak_ceiling(template: str) -> int:
    """The most this template may draw in its loudest frames.

    The same slack as the median, and that is a measured choice rather than
    a borrowed one: driven twice, the probe returned identical medians and
    p95s for all ten templates. The spread that makes this column
    interesting lives *inside* a run, not between runs, so there is no
    measurement noise here for a wider allowance to absorb.
    """

    return int(FRAME_P95[template] * FRAME_SLACK)


#: Counts every call into the canvas context, frame by frame. The context
#: is a Proxy rather than a list of known methods: a template that reached
#: for a call nobody had thought of would otherwise cost nothing.
COUNT_PROBE = """
const CALLS = [0];
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.document = { readyState: 'complete', createElement: () => nothing,
  querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => new Proxy({}, {
      get(t, k){ if (k === 'canvas') return null;
        if (typeof k === 'symbol') return () => 0;
        return function(){ CALLS[CALLS.length-1]++; return nothing } },
      set(){ return true } }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
PROBE_KEYS_PLACEHOLDER
SCRIPT_PLACEHOLDER
let F = 0;
function turn(){ if (queued) { CALLS.push(0); const fn = queued; queued = null; fn((F++) * 16) } }
function down(k){ (handlers.keydown || []).forEach(fn => fn(probeKey(k))) }
function up(k){ (handlers.keyup || []).forEach(fn => fn(probeKey(k))) }
down(' '); up(' ');
for (let i = 0; i < FRAMES_INPUT; i++) {
  if (i % 7 === 0) { down(' '); up(' ') }
  if (i % 120 < 60) { down('ArrowRight') } else { up('ArrowRight'); down('ArrowLeft') }
  if (i % 120 === 119) { up('ArrowLeft') }
  turn();
}
/* Frames that drew nothing are not frames this is about - a title screen
   or a paused page is allowed to be cheap. */
const live = CALLS.filter(n => n > 0).sort((a, b) => a - b);
console.log(JSON.stringify({ frames: live.length,
  median: live[Math.floor(live.length / 2)] || 0,
  p95: live[Math.floor(live.length * 0.95)] || 0,
  peak: live[live.length - 1] || 0 }));
"""


def count_probe(script: str, *, frames: int = 1200) -> str:
    """The page, driven by a masher, reporting its per-frame draw count."""

    return (
        COUNT_PROBE.replace("PROBE_KEYS_PLACEHOLDER", KEY_EVENT_JS)
        .replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
    )


__all__ = ["COUNT_PROBE", "FRAME_MEDIAN", "FRAME_SLACK", "count_probe", "frame_ceiling"]
