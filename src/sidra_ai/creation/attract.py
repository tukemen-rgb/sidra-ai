"""The title runs the game behind its own curtain (§17).

An attract mode is the arcade's answer to "what is this?": the cabinet
plays itself while nobody is at it, because a moving game says in a second
what three lines of text say in ten. SIDRA's title gate held the loop shut
- the template never got a frame - so a first visit was a still picture and
a paragraph.

The material was already there. C-1404's instrument proved that a racing
page drives itself to the finish with nobody touching it, which is exactly
what a demo needs: a template that produces a moving picture from no input.

Three rules, and they are the whole design:

* **The demo earns nothing.** It is not a round somebody played, so it
  banks no score, sets no best, leaves no ghost and counts no defeat. This
  is not a new rule - ``roundBank`` already refuses an untouched round
  (C-1123), and the gate is what marks a round as touched, so the demo is
  covered by the rule that already exists rather than by an exception.
* **Pressing start begins at the beginning.** The demo has moved the world,
  so it is rewound before play: the template's own ``reset`` and the round
  clock, both. Joining a demo half way through would hand somebody a
  forty-second round and a car already round the first bend.
* **It is behind a curtain, not instead of one.** The title still says what
  the game is and how to start it; the demo runs dimmed underneath.
"""

from __future__ import annotations

#: Wired here first, as the item allows. Racing is the template C-1404
#: measured driving itself to the finish line, so it is the one that
#: certainly produces a moving picture from no input at all.
ATTRACT_TEMPLATES: tuple[str, ...] = ("racing",)

#: Why each of the others is not wired yet, in the same shape as
#: ``COMBO_UNWIRED``: "not yet" and "not applicable" are different answers
#: and only the first is a backlog item. Every reason here is about what
#: the template *does* with no input, which is the only thing that decides
#: whether a demo of it is worth watching.
ATTRACT_UNWIRED: dict[str, str] = {
    "shooter": "the obvious next one: waves arrive and the held trigger is the only input a demo needs",
    "marble": "rolls itself down the corridor, but hits the first block and stops - needs a steering demo",
    "catch": "the basket never moves on its own, so the demo is items falling past a still bowl",
    "fishing": "the marker sweeps for ever and nothing else happens: motion without a game in it",
    "puzzle": "a board that is never clicked is a still image",
    "adventure": "the hero does not walk on their own; the room would sit there",
    "platformer": "same: no input means standing on the first platform until the clock",
    "kaiju": "the boss cycles but the player's shot is the whole game, and it never fires",
    "duel": "both fighters wait for a button; the screen would show two idle poses",
}

#: What to call to put the world back to its first frame. Every template
#: that has one calls it ``reset``; the expression is written down rather
#: than assumed so a template that renamed it fails the judge instead of
#: quietly starting people mid-demo.
ATTRACT_RESET: dict[str, str] = {"racing": "reset()"}


def wired(template: str) -> bool:
    """Whether this template plays itself behind the title."""

    return template in ATTRACT_TEMPLATES and template in ATTRACT_RESET


def reset_call(template: str) -> str:
    """The template's own way back to frame one, or a no-op."""

    return ATTRACT_RESET.get(template, "")




#: Runs a generated page in node: leave it alone on its title for a while,
#: then press start. The whole claim is about what happens *behind* a shut
#: gate, so the canvas is a recorder rather than a swallowing Proxy - "the
#: picture moves" is a claim about paint, and only paint can settle it.
PROBE = """
const attractNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : attractNothing),
  apply: () => attractNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
let attractClock = 0;
globalThis.performance = { now: () => attractClock };
const attractKeys = [], attractPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') attractKeys.push(fn) };
globalThis.Image = function(){ return attractNothing };
const attractStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in attractStore ? attractStore[k] : null),
  setItem: (k, v) => { attractStore[k] = String(v) },
  removeItem: (k) => { delete attractStore[k] } };
globalThis.location = { reload: () => {} };
/* Every fill, with the colour it was made in: the demo has to move, and
   the veil over it has to be a veil rather than a lid. */
let attractOps = [], attractInk = null;
globalThis.document = { readyState: 'complete',
  createElement: () => attractNothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {},
    addEventListener: (type, fn) => {
      if (type === 'pointerdown') attractPointers.push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => new Proxy({
      fillText: (t, x, y) => { attractOps.push('t:' + attractInk + ':' + String(t)
        + ':' + Math.round(Number(x) || 0) + ':' + Math.round(Number(y) || 0)) },
      fillRect: (x, y, w, h) => { attractOps.push('r:' + attractInk + ':'
        + [x, y, w, h].map(v => Math.round(Number(v) || 0)).join(',')) } }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : attractNothing)),
      set: (t, k, v) => { if (k === 'fillStyle') { attractInk = String(v) } return true } }) }) };
/* A queue, not a single slot. A gate that armed the loop *and* let the
   demo arm it would schedule two callbacks for the next frame, then four,
   then eight - and a one-slot stub would quietly drop all but the last and
   show a page that looked perfectly healthy. The browser keeps every one
   of them, so this keeps every one of them. */
let attractQueue = [];
globalThis.requestAnimationFrame = (fn) => { attractQueue.push(fn); return attractQueue.length };
SCRIPT_PLACEHOLDER
/* One number for a frame's worth of paint. A demo that is running draws a
   different picture every frame; a title with nothing behind it draws the
   same one for ever. */
function attractHash(ops){ let h = 2166136261;
  const s = ops.join('|');
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0 }
  return h }
function attractRun(frames){ const seen = [];
  for (let i = 0; i < frames && attractQueue.length; i++) {
    const due = attractQueue; attractQueue = [];
    /* A loop that is multiplying doubles every frame. Stop and report the
       count rather than running the frame: a few doublings more and the
       paint for one frame exhausts the heap, and a probe that dies is a
       probe that cannot say why. */
    if (due.length > 8) { seen.push({ hash: 0, ops: 0, calls: due.length }); break }
    attractOps = []; attractClock += 50 / 3;
    for (const fn of due) { fn(attractClock) }
    seen.push({ hash: attractHash(attractOps), ops: attractOps.length,
      calls: due.length }) }
  return seen }
/* Everything a go is made of, read off the page. Compared between a run
   that watched the demo and one that pressed at once: if the demo left
   anything behind, two snapshots taken at the same moment differ. */
function attractSnap(){
  const out = { gate: gateFacts(), attract: attractFacts(), round: roundFacts(),
    running: attractQueue.length > 0 };
  try { out.race = (typeof raceFacts === 'function') ? raceFacts() : null }
  catch (e) { out.race = null }
  try { out.ghost = (typeof ghostFacts === 'function') ? ghostFacts() : null }
  catch (e) { out.ghost = null }
  try { out.combo = (typeof comboFacts === 'function') ? comboFacts() : null }
  catch (e) { out.combo = null }
  try { out.skin = (typeof skinFacts === 'function') ? skinFacts() : null }
  catch (e) { out.skin = null }
  try { out.beats = failBeats() } catch (e) { out.beats = null }
  try { out.touched = roundTouched() } catch (e) { out.touched = null }
  out.store = JSON.parse(JSON.stringify(attractStore));
  return out }
const atLoad = attractSnap();
const idle = attractRun(IDLE_INPUT);
/* The whole of the last idle frame, kept once rather than per frame: the
   veil is a claim about one picture, and four thousand of them would be a
   megabyte of JSON to say it. */
const idlePaint = attractOps.slice();
const beforePress = attractSnap();
if (PRESS_INPUT) {
  const ev = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
  attractKeys.forEach(fn => fn(ev));
}
/* Taken before a single playing frame: whatever the demo did has to be
   gone by the time the player is handed the game, not one frame later. */
const atPress = attractSnap();
const played = attractRun(PLAY_INPUT);
const afterPlay = attractSnap();
console.log(JSON.stringify({
  atLoad: atLoad, idle: idle, idlePaint: idlePaint, beforePress: beforePress,
  atPress: atPress, played: played, afterPlay: afterPlay,
}));
"""


def probe_source(script: str, *, idle: int = 240, press: bool = True, play: int = 30) -> str:
    """The page's own script, wrapped so its title screen can be watched."""

    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("IDLE_INPUT", str(int(idle)))
        .replace("PRESS_INPUT", "true" if press else "false")
        .replace("PLAY_INPUT", str(int(play)))
    )


__all__ = [
    "ATTRACT_RESET",
    "ATTRACT_TEMPLATES",
    "ATTRACT_UNWIRED",
    "PROBE",
    "probe_source",
    "reset_call",
    "wired",
]
