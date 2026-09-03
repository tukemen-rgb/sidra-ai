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
   Returns how much the catch counter moved: 1 is a landed cast. */
function castInBand(){
  const before = fishFacts().score;
  for (let i = 0; i < 800; i++) {
    const f = fishFacts();
    if (Math.abs(f.pos - f.spot) < (f.band / 2) * 0.6) { key(' '); break }
    run(1);
  }
  run(2);
  return fishFacts().score - before;
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
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the round's sky can be watched."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = ["PROBE", "probe_source"]
