"""The fishing round's sky, judged by playing the round out (§7, C-1315).

The fishing template itself lives in :mod:`sidra_ai.creation.games` (it is
one of the two originals from before the templates got their own modules);
this module holds only the probe that watches it run.

A timing game has no course, so the round clock is the journey: the sixty
seconds split into three skies and the brightest is reserved for the last
stretch (§7 観察 5-6 over §8's round). The probe passes the briefing, lands
a cast inside the band under the first sky, lets played time carry the page
into each later act, lands another cast under the final sky, and confirms
the clock still calls the break - the arc is decoration ON the round, never
a change TO it.
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
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
/* Waits for the marker to be well inside the band, then casts once.
   Returns how many casts LANDED: 1 is a landed cast. Counted on hits,
   not points - since C-1331 a centred press pays 2, and this probe asks
   whether the throw connected, not what it was worth. */
function castInBand(){
  const before = fishFacts().hits;
  for (let i = 0; i < 800; i++) {
    const f = fishFacts();
    if (Math.abs(f.pos - f.spot) < (f.band / 2) * 0.6) { key(' '); break }
    run(1);
  }
  run(2);
  return fishFacts().hits - before;
}
/* The first press passes the briefing; played time starts here. */
key(' ');
run(30);
const early = fishFacts();
const castEarly = castInBand();
/* Let the round age into each later third. 24s and 45s sit well inside
   acts 1 and 2 of the 60s round, clear of the 20s/40s boundaries. */
let guard = 0;
while (fishFacts().ms < 24000 && guard++ < 4000) run(1);
const mid = fishFacts();
while (fishFacts().ms < 45000 && guard++ < 8000) run(1);
const late = fishFacts();
const castLate = castInBand();
/* The sky must not have touched the break: the clock still ends the go. */
while (!roundFacts().done && guard++ < 12000) run(1);
const end = roundFacts();
console.log(JSON.stringify({
  sceneEarly: early.scene, sceneMid: mid.scene, sceneLate: late.scene,
  msEarly: early.ms, msMid: mid.ms, msLate: late.ms,
  castEarly: castEarly, castLate: castLate,
  score: fishFacts().score,
  done: end.done, reason: end.reason,
  scenes: sceneFacts().scenes,
  hud: hudFacts(),
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the round's sky can be watched."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The optional danger, priced (§13, C-1331): three real presses - one in
#: the 会心 centre, one at the cautious edge of the band, one outside it -
#: and the points each was worth. The edge window is wide enough that even
#: the fastest marker cannot step across it between frames.
PRECISION_PROBE = """
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
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
/* Runs the marker until its offset from the spot, in band half-widths,
   sits inside [lo, hi], then presses once and reports what it paid. */
function pressAt(lo, hi){
  let guard = 0;
  while (guard++ < 4000) {
    const f = fishFacts();
    const off = Math.abs(f.pos - f.spot) / (f.band / 2);
    if (off >= lo && off <= hi) { break }
    run(1);
  }
  const before = fishFacts();
  key(' ');
  const after = fishFacts();
  return { gain: after.score - before.score,
    hits: after.hits - before.hits, crits: after.crits - before.crits,
    casts: after.casts - before.casts };
}
key(' ');
run(10);
const crit = fishFacts().crit;
/* Dead centre: inside the whole crit zone, so even the hard marker's
   stride cannot step over the window. */
const perfect = pressAt(0, crit);
run(4);
/* The cautious press: inside the band, clear of the crit zone. */
const careful = pressAt(0.5, 0.99);
run(4);
/* And the whiff, so the risk is real in both directions. */
const wide = pressAt(1.2, 3.0);
console.log(JSON.stringify({
  crit: crit,
  perfect: perfect, careful: careful, wide: wide,
  score: fishFacts().score, hits: fishFacts().hits,
  crits: fishFacts().crits, casts: fishFacts().casts,
}));
"""


def precision_probe(script: str) -> str:
    """The page's own script, wrapped so three throws can be priced."""

    return PRECISION_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = ["PRECISION_PROBE", "PROBE", "precision_probe", "probe_source"]
