"""Consecutive successes pay more, and the page never hides the number.

§13 事実 2: every template scores one point per thing, so a careful round
and a greedy one come out the same. Nothing in the product rewards playing
*well* as opposed to playing *long*, which is the difference between a
score worth chasing and a tally.

The smallest honest version of the fix, wired into one template first
(``catch``) so the rule can be measured on a running page before it is
spread:

* **The multiplier is a ladder, not a curve.** Three catches in a row buy
  one rung, capped at four. A curve would be untellable from the seat -
  a player has to be able to say what they did to earn it.
* **One miss takes all of it.** Not a decay and not a grace frame: the run
  is the claim, and a claim with a cushion under it is not a claim.
* **It is on screen the whole time**, at ×1 as much as at ×4. A multiplier
  a player only learns about when it fires is a slot machine; one they can
  see is a decision about whether to reach for the far item.
* **The rise is celebrated, the fall is not.** Losing the run is already
  the punishment, and a page that also shouts about it is unpleasant to
  sit in front of.

Under reduced motion the rise keeps its sound and loses its particles,
which is C-1020's rule: decoration goes, information stays. The number
itself is information, so it is drawn either way.

The score the round banks is the multiplied one, because that is the point
of the exercise - which means ``SKIN_UNIT['catch']`` had to be re-measured
rather than left as the count it used to be.
"""

from __future__ import annotations

import json

#: Wired here first. One template, so the rule can be judged on a real page
#: before nine of them inherit it.
COMBO_TEMPLATES: tuple[str, ...] = ("catch",)

#: Why each of the others is not wired yet. Written down because "not yet"
#: and "not applicable" are different answers, and only the first is a
#: backlog item.
COMBO_UNWIRED: dict[str, str] = {
    "shooter": "the obvious next one: kills are already discrete successes",
    "fishing": "a cast is a success or a miss; needs a rule for the idle sweep between casts",
    "puzzle": "clears already score by size, so a multiplier would compound an existing bonus",
    "marble": "gates are discrete, but C-1313 just made some of them worth double - two multipliers at once needs a decision",
    "adventure": "gems are placed, not earned in a run; there is nothing to be consecutive about",
    "platformer": "same as adventure - the gems are level furniture",
    "kaiju": "the cycle is the unit and there is only one target",
    "duel": "score is damage dealt, which is already a rate rather than a count",
    "racing": "laps are the score and there are two or three of them",
}

#: Consecutive successes per rung. Three, measured against catch's own
#: pace: on normal an item falls about every 22 frames, so one rung is
#: roughly a second of clean play - long enough to be a run, short enough
#: that a 60-second round can reach the top and lose it several times.
COMBO_STEP = 3

#: The top rung. Four is §13's own example, and past it the last catch of a
#: round outweighs the first thirty, which stops being a score.
COMBO_MAX = 4

#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``comboMult`` would break
#: only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "comboHit",
    "comboMiss",
    "comboMult",
    "comboRun",
    "comboLabel",
    "comboFacts",
)

COMBO_PREAMBLE = """
/* --- consecutive successes pay more (§13 事実 2) -------------------- */
const COMBO_STEP=COMBO_STEP_TOKEN,COMBO_MAX=COMBO_MAX_TOKEN;
let COMBO_RUN=0,COMBO_MULT=1;
function comboRun(){return COMBO_RUN}
function comboMult(){return COMBO_MULT}
/* Drawn at x1 as much as at x4: a multiplier a player only meets when it
   fires is a slot machine, one they can watch is a decision. */
function comboLabel(){return '\u00d7'+COMBO_MULT}
/* The rise, and only the rise. Losing the run is punishment enough, so
   there is no sound for the fall. Under reduced motion the particles go
   and the sound stays - decoration is what C-1020 drops, not information.
   Every effect is guarded: this preamble sits above templates that are
   allowed not to have a canvas. */
function comboCheer(){
  try{sfx('gem')}catch(e){}
  if(typeof REDUCED!=='undefined'&&REDUCED)return;
  try{shake(3)}catch(e){}
  try{burst(cv.width/2,40,12,'ACCENT_JUICE')}catch(e){}}
/* Returns the multiplier this success is worth, so the caller adds points
   rather than asking twice and risking the two answers disagreeing. */
function comboHit(){COMBO_RUN++;
  const next=Math.min(COMBO_MAX,1+Math.floor(COMBO_RUN/COMBO_STEP));
  if(next>COMBO_MULT){COMBO_MULT=next;comboCheer()}
  return COMBO_MULT}
/* One miss takes all of it. No decay, no grace frame: a run with a
   cushion under it is not a run. */
function comboMiss(){COMBO_RUN=0;COMBO_MULT=1}
function comboFacts(){return {run:COMBO_RUN,mult:COMBO_MULT,
  step:COMBO_STEP,max:COMBO_MAX}}
"""


def preamble_for(template: str) -> str:
    """The rule, for the templates that have consecutive successes."""

    if template not in COMBO_TEMPLATES:
        return ""
    return COMBO_PREAMBLE.replace("COMBO_STEP_TOKEN", str(COMBO_STEP)).replace(
        "COMBO_MAX_TOKEN", str(COMBO_MAX)
    )




#: The probe. Drives the real generated page rather than re-implementing
#: the rule: the basket is steered onto the next item to force a catch, or
#: away from it to force a miss, and every frame's ``comboFacts()``, score
#: and HUD line are recorded. A rule that stopped being wired would show up
#: here as a flat timeline rather than as a passing unit test.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
let rnd = 2463534242;
Math.random = () => { rnd ^= rnd << 13; rnd ^= rnd >>> 17; rnd ^= rnd << 5;
  return ((rnd >>> 0) % 100000) / 100000 };
class D { constructor(){ return D.parse() }
  static parse(){ return { getFullYear: () => 2026, getMonth: () => 8, getDate: () => 3 } } }
globalThis.Date = D;
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
let clock = 0;
globalThis.performance = { now: () => clock };
const keys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') keys.push(fn) };
globalThis.Image = function(){ return nothing };
const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v) }, removeItem: (k) => { delete store[k] } };
Object.defineProperty(globalThis, 'navigator', { configurable: true, writable: true,
  value: { clipboard: { writeText: () => {} } } });
/* Every line the page drew this frame, so "is the multiplier on screen"
   is asked of the page rather than of the source. */
let drawn = [];
const ctx = new Proxy({ fillText: (t) => { drawn.push(String(t)) } },
  { get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true });
const moves = [];
const canvas = { width: 720, height: 320, style: {},
  addEventListener: (type, fn) => { if (type === 'pointermove') moves.push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => ctx };
function element(tag){ return { tagName: tag, style: {}, children: [], attrs: {},
  appendChild(c){ this.children.push(c); return c }, remove(){}, select(){},
  setAttribute(k, v){ this.attrs[k] = v }, getAttribute(k){ return this.attrs[k] },
  addEventListener(){}, getBoundingClientRect: () => ({left:0,top:0,width:720,height:320}),
  getContext: () => ctx, width: 720, height: 320 } }
globalThis.document = { readyState: 'complete', body: element('body'),
  createElement: element, querySelector: () => null, execCommand: () => true,
  getElementById: () => canvas };
globalThis.location = { reload: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* Counted after the page is built, so the celebration can be told apart
   from the catch's own effects by when it fires. */
let bursts = 0, shakes = 0, sounds = [];
const realBurst = burst, realShake = shake, realSfx = sfx;
burst = (...a) => { bursts++; return realBurst(...a) };
shake = (...a) => { shakes++; return realShake(...a) };
sfx = (n) => { sounds.push(String(n)); return realSfx(n) };
/* Read the briefing, the way a player does: the gate holds the loop
   until a key arrives, so a probe that never presses one measures a
   start screen. */
function press(code){ const ev = { key: code, code: code, clientX: 360, clientY: 160,
  preventDefault(){}, stopImmediatePropagation(){} };
  keys.forEach(fn => fn(ev)); return ev }
function pump(n){ for (let i = 0; i < n && queued; i++) {
  const fn = queued; queued = null; clock += 50 / 3; fn(clock) } }
pump(2); press('Space'); pump(2);
/* Which items to drop on purpose, in the order they land. */
const missSet = new Set(MISSES_INPUT);
let resolved = 0, last = 0;
const timeline = [];
for (let f = 0; f < FRAMES_INPUT && queued; f++) {
  /* Steer before the frame runs: the next item to land is the head of the
     queue, because one spawns every FALL frames and they are filtered in
     order. Both the target and the eased position are set, so the probe
     measures the combo rule rather than the basket's easing. */
  if (items.length) {
    const aim = missSet.has(resolved) ? (items[0].x > 0.5 ? 0.02 : 0.98) : items[0].x;
    px = aim; shown = aim }
  const before = { bursts, shakes, sounds: sounds.length };
  const fn = queued; queued = null; clock += 50 / 3; fn(clock);
  const now = score + 0;
  const settled = caught + missed;
  if (settled !== last) {
    last = settled; resolved = settled;
    timeline.push({ at: f, kind: now !== undefined && caught > 0 ? 'x' : 'x',
      caught, missed, score, mult: comboMult(), run: comboRun(),
      rose: bursts - before.bursts, rang: sounds.slice(before.sounds),
      hud: drawn.filter(t => t.indexOf('得点') === 0)[0] || null }) }
  drawn = [] }
console.log(JSON.stringify({ timeline, facts: comboFacts(),
  score, caught, missed, bursts, shakes }));
"""


def probe_source(script: str, *, frames: int = 2000, misses=(), reduced: bool = False) -> str:
    """One page, steered: catch everything except the named landings."""

    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("MISSES_INPUT", json.dumps([int(i) for i in misses]))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
    )


__all__ = [
    "COMBO_MAX",
    "PROBE",
    "COMBO_PREAMBLE",
    "COMBO_STEP",
    "COMBO_TEMPLATES",
    "COMBO_UNWIRED",
    "PREAMBLE_NAMES",
    "preamble_for",
    "probe_source",
]
