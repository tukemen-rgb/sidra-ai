"""The catch round's sky, judged by playing the round out (§7, C-1319).

The catch template itself lives in :mod:`sidra_ai.creation.games` (it is
one of the two originals from before the templates got their own modules,
like fishing's); this module holds only the probe that watches it run.

The catch half of C-1315: the second clock-bound template gets its three
skies, and the probe proves them the same way - pass the briefing, land a
catch under the first sky by steering the basket under the lowest falling
item, let played time carry the page into each later third, land another
under the final sky, and confirm the clock still calls the break.
"""

from __future__ import annotations

#: The page driven in node, the same no-op browser the template probes
#: build. Frames tick 16ms apart, which is the clock ``ROUND_MS`` reads.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(k){
  const e = { key: k, code: k, preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
}
/* Steers the basket under the lowest falling item until one more catch
   lands. Returns how much the catch counter moved: 1+ is a landed catch. */
function catchOne(){
  const before = catchFacts().score > -1 ? caught : caught;
  for (let i = 0; i < 900; i++) {
    const low = items.reduce((a, b) => (a === null || b.y > a.y ? b : a), null);
    if (low) { px = low.x }
    run(1);
    if (caught > before) return caught - before;
  }
  return 0;
}
/* The first press passes the briefing; played time starts here. */
key(' ');
run(30);
const early = catchFacts();
const caughtEarly = catchOne();
/* Let the round age into each later third. 24s and 45s sit well inside
   acts 1 and 2 of the 60s round, clear of the 20s/40s boundaries. */
let guard = 0;
while (catchFacts().ms < 24000 && guard++ < 4000) run(1);
const mid = catchFacts();
while (catchFacts().ms < 45000 && guard++ < 8000) run(1);
const late = catchFacts();
const caughtLate = catchOne();
/* The sky must not have touched the break: the clock still ends the go. */
while (!roundFacts().done && guard++ < 12000) run(1);
const end = roundFacts();
console.log(JSON.stringify({
  sceneEarly: early.scene, sceneMid: mid.scene, sceneLate: late.scene,
  msEarly: early.ms, msMid: mid.ms, msLate: late.ms,
  caughtEarly: caughtEarly, caughtLate: caughtLate,
  caught: catchFacts().caught, score: catchFacts().score,
  done: end.done, reason: end.reason,
  scenes: sceneFacts().scenes,
  hud: hudFacts(),
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the round's sky can be watched."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: Held movement, measured the way the on-screen pad actually presses
#: (§12 事実 3, C-1328): exactly one keydown, no synthetic repeats, one
#: keyup at the end. The basket must nudge on the press, keep drifting
#: every frame while held (an OS repeat must NOT be a second nudge), stop
#: the frame the key is released, and never leave the field. Whether the
#: catching underneath still works stays the scene probe's question - it
#: steers and lands catches on this same template every run.
HOLD_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function kd(k){ (handlers.keydown || []).forEach(fn => fn({ key: k,
  code: k === ' ' ? 'Space' : k, preventDefault(){}, stopImmediatePropagation(){} })) }
function ku(k){ (handlers.keyup || []).forEach(fn => fn({ key: k,
  code: k === ' ' ? 'Space' : k, preventDefault(){}, stopImmediatePropagation(){} })) }
/* Past the briefing; the keyboard drives px, so the pointer-easing shown
   is not read at all - px is the truth the keys write. */
kd(' '); ku(' ');
run(10);
const px0 = catchFacts().px;
kd('ArrowLeft');                    // one press, exactly like the pad
const pxNudge = catchFacts().px;    // the tap step lands inside the event
kd('ArrowLeft');                    // an OS auto-repeat while already held
const pxRepeat = catchFacts().px;   // ...must not be a second step
run(30);
const pxHeld = catchFacts().px;     // the loop kept it moving
ku('ArrowLeft');
const pxStop1 = catchFacts().px;
run(10);
const pxStop2 = catchFacts().px;    // released means stopped
kd('ArrowLeft');
run(200);                           // long hold: the field edge holds
const pxEdge = catchFacts().px;
ku('ArrowLeft');
console.log(JSON.stringify({
  px0: px0, pxNudge: pxNudge, pxRepeat: pxRepeat, pxHeld: pxHeld,
  pxStop1: pxStop1, pxStop2: pxStop2, pxEdge: pxEdge,
}));
"""


def hold_probe(script: str) -> str:
    """The page's own script, wrapped so a held key can be watched."""

    return HOLD_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The receiving half of squash & stretch (§1, C-1341), watched on a real
#: catch: the basket reads 1 before the impact, squashes below 0.9 on the
#: catch frame, settles back to 1 within half a second, and never deforms
#: while nothing lands. The reduced-motion run is the other half of the
#: claim: every sampled frame reads exactly 1.
BOUNCE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(k){
  const e = { key: k, code: k, preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
}
key(' ');
run(30);
/* Idle first: nothing has landed, so the basket must hold its shape -
   steered away from every item so no accidental catch muddies the read. */
let idleOff = 0;
for (let i = 0; i < 40; i++) { px = 0.05; run(1);
  if (catchFacts().squash !== 1) idleOff++ }
/* Then one real catch, with the squash sampled every frame around it. */
const before = caught;
let catchSq = null, timeline = [];
for (let i = 0; i < 900 && catchSq === null; i++) {
  const low = items.reduce((a, b) => (a === null || b.y > a.y ? b : a), null);
  if (low) { px = low.x }
  run(1);
  if (caught > before) { catchSq = catchFacts().squash } }
for (let i = 0; i < 40; i++) { px = 0.05; run(1); timeline.push(catchFacts().squash) }
console.log(JSON.stringify({
  idleOff: idleOff, catchSq: catchSq,
  minAfter: Math.min.apply(null, timeline),
  settled: timeline[timeline.length - 1],
  caught: caught,
}));
"""


def bounce_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the basket's shape can be watched."""

    return BOUNCE_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


__all__ = [
    "BOUNCE_PROBE",
    "HOLD_PROBE",
    "PROBE",
    "bounce_probe",
    "hold_probe",
    "probe_source",
]
