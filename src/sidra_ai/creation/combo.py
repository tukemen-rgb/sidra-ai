"""Consecutive successes pay more, and the page never hides the number.

§13 事実 2: every template scores one point per thing, so a careful round
and a greedy one come out the same. Nothing in the product rewards playing
*well* as opposed to playing *long*, which is the difference between a
score worth chasing and a tally.

The smallest honest version of the fix, wired one template at a time so
each can be measured on a running page before the next inherits it
(``catch`` first, then ``shooter``):

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
of the exercise - which means ``SKIN_UNIT`` had to be re-measured for each
template wired rather than left as the count it used to be.

On ``shooter`` the multiplier rides the kills and nothing else. Graze
(C-1406) pays its own points for flying close, and the two are added but
never multiplied together: one is a risk taken, the other a run kept, and
a player who does both should be paid for both rather than for the product
of them. The raw kill count stays on screen beside the points, because
「撃墜 N 機」 is a count and the score no longer is.
"""

from __future__ import annotations

import json

#: Wired one template at a time, each judged on a running page before the
#: next. ``catch`` first (C-1405), then ``shooter`` (C-1411): a kill is
#: already a discrete success and a hull already ends a run, so the rule
#: needed a place to add points and a place to drop them and nothing else.
#:
#: ``marble`` third (C-1420). This table used to say it needed a decision
#: first, because C-1313 had made some gates worth double and two
#: multipliers at once is one too many. The decision: **the run multiplies
#: the gate's base value, and the hot gate's extra is added outside it.**
#: A hot gate on a x3 run pays 3 + 1, not 6. Stacking them would make the
#: best line on the course the one a player cannot work out from the seat,
#: which is exactly what §13's readable risk is against - and it is the
#: same call C-1411 made when it added the graze to the kills rather than
#: multiplying the two together.
#:
#: The run breaks on a gate passed outside the posts. The entry said
#: 「落下」; there is no fall in that corridor. Hitting a block ends the go
#: outright, so a missed gate is the only thing a player can do wrong and
#: keep playing - which is what a run has to be breakable by.
#: ``fishing`` fourth (C-1426). This table used to say it needed a rule
#: for the idle sweep between casts, and that is the decision: **the sweep
#: is not a miss.** Only a cast can break the run, because a player who is
#: waiting for the marker to come back around is doing the thing the game
#: asks for, and a run that drained while they waited would make patience
#: the punished move - the opposite of §13's readable risk. So the run
#: breaks on a cast that landed outside the band, and on nothing else.
#:
#: 会心 (C-1331) already pays double, so this is the same sum C-1420 chose
#: for marble: the multiplier rides the cast's base value and the perfect
#: throw's extra is added outside it. A 会心 on a x3 run pays 3 + 1, not 6.
COMBO_TEMPLATES: tuple[str, ...] = ("catch", "shooter", "marble", "fishing")

#: Why each of the others is not wired yet. Written down because "not yet"
#: and "not applicable" are different answers, and only the first is a
#: backlog item.
COMBO_UNWIRED: dict[str, str] = {
    "puzzle": "clears already score by size, so a multiplier would compound an existing bonus",
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
  /* The step-up is a power-up, not a 47th pickup (§2, C-1339): the
     multiplier rising is rare and earned, and it gets sfxr's powerUp
     shape - rising tone with vibrato - instead of the gem's sweep. */
  try{sfx('powerup')}catch(e){}
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


#: The shooter's probe (C-1411). The catch probe steers a basket; a fight
#: needs a pilot, so this one reuses the shooter's own: hold the trigger,
#: sidestep whatever is at the ship's altitude, and otherwise sit under the
#: lowest hull so the field thins. After ``CRASH_AT`` it stops dodging and
#: walks into the nearest hull on purpose, which is the only way to watch a
#: run end. Every kill and every hull is recorded with the page's own
#: ``comboFacts()``, score, graze count and HUD line.
SHOOTER_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let drawn = [];
const ctx = new Proxy({ fillText: (t) => { drawn.push(String(t)) } },
  { get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true });
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => ctx }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* Wrapped after the page is built, so the celebration can be told from the
   kill's own effects by when it fires. */
let bursts = 0, sounds = [];
const realBurst = burst, realSfx = sfx;
burst = (...a) => { bursts++; return realBurst(...a) };
sfx = (n) => { sounds.push(String(n)); return realSfx(n) };
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) {
  const fn = queued; queued = null; fn((F++) * 16) } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e)) }
/* Past the briefing, then hold the trigger for the whole run. */
key('keydown', ' '); key('keyup', ' ');
run(2);
key('keydown', ' ');
function nearest(){ let best = null, bd = 1e9;
  foes.forEach(f => { if (f.hp <= 0) return;
    const d = Math.hypot(f.x - ship.x, f.y - ship.y);
    if (d < bd) { bd = d; best = f } });
  return best ? { foe: best, dist: bd } : null }
const CRASH_AT = CRASH_AT_INPUT;
const timeline = [];
let lastKills = 0, lastHp = null, lastScore = 0;
for (let f = 0; f < FRAMES_INPUT && shooterFacts().state === 'play'; f++) {
  const now = shooterFacts();
  key('keyup', 'ArrowLeft'); key('keyup', 'ArrowRight');
  let goal = null;
  if (f >= CRASH_AT) {
    /* Stop flying and take the hull. Steering by key, so the ship moves
       at the speed the template gives it. */
    const near = nearest();
    if (near) goal = near.foe.x;
  } else {
    const im = now.incoming.filter(([fx, fy]) => fy > 226 && fy < 330);
    if (im.some(([fx]) => Math.abs(fx - now.x) < 40)) {
      let bestClear = -1e9, bestSafe = null, best = now.x;
      for (let x = 26; x <= now.w - 26; x += 8) {
        let clear = 1e9;
        im.forEach(([fx]) => { clear = Math.min(clear, Math.abs(x - fx)) });
        const lo = Math.min(now.x, x), hi = Math.max(now.x, x);
        const blocked = im.some(([fx]) => fx > lo - 28 && fx < hi + 28);
        const sc = Math.min(clear, 120) - Math.abs(x - now.x) * 0.02;
        if (sc > bestClear) { bestClear = sc; best = x }
        if (!blocked && (bestSafe === null || sc > bestSafe[1])) bestSafe = [x, sc];
      }
      goal = bestSafe ? bestSafe[0] : best;
    } else {
      let ty = -1;
      now.incoming.forEach(([fx, fy]) => { if (fy <= 226 && fy > ty) { ty = fy; goal = fx } });
    }
  }
  if (goal !== null && goal < now.x - 4) key('keydown', 'ArrowLeft');
  else if (goal !== null && goal > now.x + 4) key('keydown', 'ArrowRight');
  /* Two shots can land on two hulls in one frame, so a frame is not a
     kill. The multiplier standing *before* the frame is recorded with the
     one standing after it, and the number of kills between them, because
     a payout spanning a rung is the sum of two rungs rather than twice
     either (C-1411). */
  const before = { bursts, sounds: sounds.length, mult: now.combo.mult };
  run(1);
  const after = shooterFacts();
  const hit = lastHp !== null && after.hp < lastHp;
  if (after.kills !== lastKills || hit) {
    timeline.push({ at: f, kills: after.kills, score: after.score,
      gained: after.score - lastScore, took: after.kills - lastKills,
      hit: hit, was: before.mult,
      mult: after.combo.mult, run: after.combo.run, hp: after.hp,
      paid: after.graze.paid, seen: after.graze.seen,
      rose: bursts - before.bursts, rang: sounds.slice(before.sounds),
      hud: drawn.filter(t => t.indexOf('\u5f97\u70b9') === 0)[0] || null });
    lastKills = after.kills; lastScore = after.score }
  lastHp = after.hp;
  drawn = [] }
const end = shooterFacts();
console.log(JSON.stringify({ timeline, combo: end.combo, graze: end.graze,
  score: end.score, kills: end.kills, hp: end.hp, t: end.t,
  state: end.state, roundScore: roundScore(), step: COMBO_STEP, max: COMBO_MAX }));
"""


def shooter_probe_source(
    script: str, *, frames: int = 1800, crash_at: int | None = None, reduced: bool = False
) -> str:
    """Fly the fight, optionally walking into a hull once a run is built."""

    return (
        SHOOTER_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("CRASH_AT_INPUT", "1e9" if crash_at is None else str(int(crash_at)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
    )


__all__ = [
    "COMBO_MAX",
    "PROBE",
    "SHOOTER_PROBE",
    "COMBO_PREAMBLE",
    "COMBO_STEP",
    "COMBO_TEMPLATES",
    "COMBO_UNWIRED",
    "PREAMBLE_NAMES",
    "preamble_for",
    "probe_source",
    "shooter_probe_source",
]
