"""Screen shake, hitstop and particles - the half of game feel after sound.

The knowledge base (``docs/research/game-design-notes.md`` §1) puts the
order plainly: sound first, then shake and hitstop, then particles. C-1017
did the sound. This is the rest, and it is built the same way - one preamble
shared by every template, so a new template gets feel from the day it is
written rather than the day someone remembers to add it.

Three effects, each with a reason for the shape it has:

* ``shake(weight)`` kicks the **canvas element** and decays fast. Vlambeer's
  rule is that the kick is proportional to the weight of the event; a
  constant rattle reads as a bug. Moving the element rather than every draw
  call means no template has to cooperate with the camera.
* ``hitstop(frames)`` freezes the loop for a few frames by re-scheduling the
  animation callback without running it. The frame that was already drawn
  stays on screen, which is what a hit landing is supposed to feel like -
  and, unlike a flag templates have to check, it cannot be half-applied.
* ``burst(x, y, n, colour)`` spawns particles drawn after the game each
  frame. Templates only say where and how many.

**Reduced motion**: ``shake`` and ``burst`` become no-ops - that is the
setting's whole point, and §1 is explicit that these are the decorative
half. ``hitstop`` stays: it moves nothing, it withholds motion, and a person
who asked for less movement is not asking for hits to feel weightless. The
game is fully playable with all three off; ``probe_source`` runs the code
both ways so this is measured rather than asserted.
"""

from __future__ import annotations

import json

#: Names the preamble introduces. Held to by a test, as with the animation
#: preamble: a template that happened to define ``shake`` would break only in
#: the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "shake",
    "hitstop",
    "burst",
    "shakeAmount",
    "particleCount",
    "failBeat",
    "failBeats",
    "failBeatsReset",
    "winBeat",
    "winBeats",
    "flashGate",
    "flashCount",
    "haptic",
    "hapticOn",
    "hapticFacts",
    "scorePop",
    "popFacts",
)

#: The third sense (§16). Milliseconds, and deliberately short: a buzz you
#: notice is a buzz that is already too long on a phone held in one hand.
#: A hit is one tap; a round confirming itself is two, which is the same
#: "one event / one summary" shape the sound and the banner already use.
HAPTIC_HIT = 18
HAPTIC_ROUND = (12, 60, 12)

#: How many pulses may fire inside one 60-frame window. The same number and
#: the same window as the flash gate (§15, C-1320), for the same reason: a
#: rattling phone is not feedback, and the fourth pulse in a second carries
#: nothing the first three did not.
HAPTIC_MAX = 3

#: How many 「+N」 can be on screen at once (C-1418 条件②). A shooter wave
#: can pay four or five times inside a second, and a screen papered with
#: numbers hides the game the numbers are about. Four is the most that fits
#: without the play field becoming a scoreboard; past that the oldest is
#: dropped, because it has already had its moment.
POP_MAX = 4

#: Frames a 「+N」 lasts, and how far it drifts up each one. Short: it is a
#: receipt, not a label. 36 frames is about six tenths of a second, long
#: enough to read a two-digit number and gone before the next one lands.
POP_LIFE = 36
POP_RISE = 0.55

#: The failure beat's three numbers, in the units the effects above take.
#: Deliberately heavier than any hit: §8 事実 2 is that losing a round felt
#: the same as being hit, so the moment a go ends had no shape. The
#: heaviest hit in the templates is the shooter's 11, so the beat is 14.
FAIL_SHAKE = 14
FAIL_HITSTOP = 7
FAIL_PARTICLES = 20

#: The victory beat's numbers (C-1316). Heavier than the failure's, not
#: just heavier than a hit: §6 puts the biggest moment of the whole fight
#: at the takedown, and §1 scales the kick to the weight of the event -
#: yet every template's win used to be *lighter* than its loss (marble's
#: was silent). The win is the heaviest thing a round can show.
WIN_SHAKE = 16
WIN_HITSTOP = 7
WIN_PARTICLES = 26

JUICE_PREAMBLE = """
/* --- juice: shake, hitstop, particles (knowledge base §1) ------------- */
const JCV=document.getElementById('stage');
let SHAKE=0,HITSTOP=0,PARTS=[];
/* Weight in "how big was this": 1 a footstep, 6 a hit, 12 a death. The kick
   is that many pixels and is gone in a few frames. */
function shake(weight){if(REDUCED)return;SHAKE=Math.max(SHAKE,weight)}
function hitstop(frames){HITSTOP=Math.max(HITSTOP,frames)}
function burst(x,y,n,colour){if(REDUCED)return;
  for(let i=0;i<n;i++){const a=Math.random()*Math.PI*2,s=0.6+Math.random()*1.8;
    PARTS.push({x:x,y:y,vx:Math.cos(a)*s,vy:Math.sin(a)*s-0.6,
      life:1,c:colour||'CYAN_TOKEN'})}}
function shakeAmount(){return SHAKE}
function particleCount(){return PARTS.length}
/* The moment a round is lost, as one call (§8 事実 2). Built out of the
   three effects above rather than beside them, so reduced motion needs no
   second opinion: the shake and the particles are already no-ops, and the
   hitstop - which withholds motion instead of adding it - is what carries
   the beat for a viewer who asked for less. */
let FAIL_BEATS=0;
function failBeat(x,y){FAIL_BEATS++;
  shake(%(shake)d);hitstop(%(hitstop)d);
  burst(x===undefined?0:x,y===undefined?0:y,%(parts)d,'ALERT_JUICE');
  try{sfx('lose')}catch(e){}
  /* The shared moment of impact, and the only one there is: `hitstop` is
     called by successes too (a cleared puzzle, a hit on the boss), so it
     is not "took a hit" and cannot carry this (C-1413). */
  try{haptic(%(hapticHit)d)}catch(e){}}
function failBeats(){return FAIL_BEATS}
/* Per round, not per page (C-1122). The counter used to run for the life
   of the tab, so in a template that restarts in place - the duel's R,
   kaiju's tap - every round after the first loss was recorded as a loss
   too: 29 straight wins were measured as a streak of 30 defeats, which is
   the difficulty easing for somebody who is winning. */
function failBeatsReset(){FAIL_BEATS=0}
/* The moment a round is WON, as one call (C-1316). The mirror of the
   failure beat, one step heavier: §6 spends the biggest moment on the
   takedown, and before this every template's victory was lighter than its
   loss - marble's was silent. Accent-coloured where the failure is alert,
   the win sound where the failure has the lose sound, and reduced motion
   is inherited the same way: shake and burst are already no-ops, the
   hitstop carries the beat. */
let WIN_BEATS=0;
function winBeat(x,y){WIN_BEATS++;
  shake(%(wshake)d);hitstop(%(whitstop)d);
  burst(x===undefined?0:x,y===undefined?0:y,%(wparts)d,'ACCENT_JUICE');
  try{sfx('win')}catch(e){}}
function winBeats(){return WIN_BEATS}
/* The flash budget (§15, WCAG 2.3.1): a full-screen flash may switch ON
   at most three times in any one second - measured, the duel's mash fire
   at match-point tempo hit four. A template asks this gate before
   re-arming its overlay; the fourth onset in a rolling 60-frame window
   is refused, the first three - and the decay already on screen - are
   untouched, so the effect survives and the strobe cannot. The area
   exemption does not apply: the overlays cover the whole canvas, far
   over the quarter-of-10-degrees rectangle (§15 事実 2). */
let FLASH_TIMES=[],FLASH_FRAME=0;
function flashGate(){
  FLASH_TIMES=FLASH_TIMES.filter(t=>FLASH_FRAME-t<60);
  if(FLASH_TIMES.length>=3)return false;
  FLASH_TIMES.push(FLASH_FRAME);return true}
function flashCount(){return FLASH_TIMES.length}
/* --- the third sense (§16) -------------------------------------------
   `navigator.vibrate` is one line and no dependency, and on a device that
   does not have it the call is silently ignored by the spec rather than
   throwing. That is the whole reason this can be added at all: it is
   Android Chrome only (caniuse, 2026-09-04), so it may never be the only
   way something is said. Everything here is *also* on screen and in the
   sound already - this adds a third channel to moments that have two.

   Three gates, in this order: reduced motion silences it like every other
   decoration (C-1020 - information stays, decoration goes, and a buzz is
   decoration by construction since nothing is told only this way); the
   panel switch is next to the volume dial; and the window gate below
   stops a run of hits from rattling the phone continuously. */
let HAPTIC_TIMES=[],HAPTIC_FRAME=0,HAPTIC_N=0,HAPTIC_SENT=[];
function hapticOn(){try{return tuneFlag('haptic',true)}catch(e){return true}}
function hapticGate(){
  HAPTIC_TIMES=HAPTIC_TIMES.filter(t=>HAPTIC_FRAME-t<60);
  if(HAPTIC_TIMES.length>=%(hapticMax)d)return false;
  HAPTIC_TIMES.push(HAPTIC_FRAME);return true}
/* Returns whether it fired, so a caller can be judged on the decision
   rather than on whether a phone was attached. */
function haptic(pattern){
  if(REDUCED)return false;
  if(!hapticOn())return false;
  if(!hapticGate())return false;
  HAPTIC_N++;
  if(HAPTIC_SENT.length<50){HAPTIC_SENT.push(pattern)}
  try{if(typeof navigator!=='undefined'&&navigator&&
    typeof navigator.vibrate==='function'){navigator.vibrate(pattern)}}catch(e){}
  return true}
function hapticFacts(){return {on:hapticOn(),fired:HAPTIC_N,
  window:HAPTIC_TIMES.length,max:%(hapticMax)d,sent:HAPTIC_SENT.slice()}}
function stepShake(){if(!JCV)return;
  if(SHAKE>0.05){SHAKE*=0.78;
    const dx=(Math.random()*2-1)*SHAKE,dy=(Math.random()*2-1)*SHAKE;
    JCV.style.transform='translate('+dx.toFixed(2)+'px,'+dy.toFixed(2)+'px)'}
  else if(SHAKE!==0){SHAKE=0;JCV.style.transform=''}}
function stepParticles(){if(!PARTS.length||!JCV)return;
  const c=JCV.getContext('2d');c.save();
  PARTS=PARTS.filter(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=0.12;p.life-=0.045;
    if(p.life<=0)return false;
    c.globalAlpha=Math.max(0,p.life);c.fillStyle=p.c;
    c.fillRect(p.x-1.5,p.y-1.5,3,3);return true});
  c.restore()}
/* --- 得点が入った場所に「+N」 (§1, C-1418) ----------------------------- */
/* The score has only ever moved as a total in the corner, so which act
   paid what was arithmetic the player had to do in their head. This says
   it where it happened.

   The number is *returned*, so a call site reads `score+=scorePop(x,y,n)`
   and the float cannot disagree with the score: they are one value, not
   two that have to be kept in step. A decoration that says 「+5」 while 3
   goes in is worse than no decoration - it is the page lying about the
   only thing the player is trying to learn. */
let POPS=[],POP_SHOWN=0,POP_DROPPED=0,POP_TOTAL=0;
const POP_MAX=%(popMax)d,POP_LIFE=%(popLife)d,POP_RISE=%(popRise)s;
function scorePop(x,y,n){
  if(typeof n!=='number'||!isFinite(n)||n<=0)return n;
  /* Same rule as the particles: a decoration, and 条件① says decorations
     go quiet for somebody who asked for less motion. The score itself is
     unaffected - it is returned above and below this line alike. */
  if(REDUCED)return n;
  /* 条件②: a wave that scores eight times in one frame must not paper the
     screen over the game being played. The oldest ones have had their
     moment, so the newest wins the slot - and the drop is counted, so the
     cap is a number the judge can read rather than a claim. */
  if(POPS.length>=POP_MAX){POPS.shift();POP_DROPPED++}
  POPS.push({x:x,y:y,n:n,life:1});POP_SHOWN++;POP_TOTAL+=n;
  return n}
function stepPops(){if(!POPS.length||!JCV)return;
  const c=JCV.getContext('2d');
  c.save();c.textAlign='center';c.font='13px ui-monospace,monospace';
  POPS=POPS.filter(function(p){
    p.life-=1/POP_LIFE;p.y-=POP_RISE;
    if(p.life<=0)return false;
    c.globalAlpha=Math.max(0,Math.min(1,p.life));
    c.fillStyle='ACCENT_JUICE';c.fillText('+'+p.n,p.x,p.y);
    return true});
  c.restore()}
function popFacts(){return {live:POPS.length,shown:POP_SHOWN,
  dropped:POP_DROPPED,max:POP_MAX,reduced:REDUCED,total:POP_TOTAL,
  said:POPS.map(function(p){return p.n})}}
/* The loop wrapper does three jobs in one place: hold the frame during a
   hitstop, draw the particles over whatever the game drew, and move the
   canvas. Wrapped before the pad wraps it, so the pad stays on top. */
const JUICE_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return JUICE_RAF(function tick(t){
    /* Re-scheduled rather than skipped: dropping the callback would end the
       template's loop instead of pausing it. */
    if(HITSTOP>0){HITSTOP--;JUICE_RAF(tick);return}
    FLASH_FRAME++;HAPTIC_FRAME++;
    fn(t);stepParticles();stepPops();stepShake()})};
""" % {
    "shake": FAIL_SHAKE,
    "hitstop": FAIL_HITSTOP,
    "parts": FAIL_PARTICLES,
    "hapticHit": HAPTIC_HIT,
    "hapticMax": HAPTIC_MAX,
    "popMax": POP_MAX,
    "popLife": POP_LIFE,
    "popRise": POP_RISE,
    "wshake": WIN_SHAKE,
    "whitstop": WIN_HITSTOP,
    "wparts": WIN_PARTICLES,
}

#: Runs the three effects with the viewer's setting pinned, and prints what
#: they did. The metric executes this in node, so "reduced motion turns the
#: decoration off" is observed rather than grepped.
PROBE = """
globalThis.matchMedia = (q) => ({ matches: REDUCED_INPUT });
globalThis.document = { getElementById: () => null };
globalThis.requestAnimationFrame = (fn) => 0;
ANIMATION_PLACEHOLDER
JUICE_PLACEHOLDER
shake(8);
burst(10, 10, 12, '#fff');
hitstop(4);
const plain = { shake: shakeAmount(), particles: particleCount(), hitstop: HITSTOP };
/* The victory beat, through the same switches (C-1316): its shake and
   particles are the no-ops reduced motion already made them, its hitstop
   stays, and it counts itself exactly once. */
winBeat(5, 5);
console.log(JSON.stringify({
  reduced: REDUCED,
  shake: plain.shake,
  particles: plain.particles,
  hitstop: plain.hitstop,
  winShake: shakeAmount(),
  winParticles: particleCount() - plain.particles,
  winHitstop: HITSTOP,
  winBeats: winBeats(),
}));
"""


def probe_source(*, reduced: bool) -> str:
    """The harness with the viewer's setting pinned, ready for ``node -``."""

    from sidra_ai.creation.animation import PREAMBLE as ANIMATION_PREAMBLE

    return (
        PROBE.replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("ANIMATION_PLACEHOLDER", ANIMATION_PREAMBLE)
        .replace("JUICE_PLACEHOLDER", JUICE_PREAMBLE)
    )


#: The haptics probe (C-1413). The preamble probe above runs the kit on its
#: own; this one drives a whole generated page, because the two moments
#: being judged - a failure beat and a round confirming itself - are only
#: reachable by playing. ``navigator.vibrate`` is recorded rather than
#: stubbed away, so what the page asked the device for is what gets read.
PAGE_PROBE = """
const hNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : hNothing),
  apply: () => hNothing, set: () => true });
const hHandlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (hHandlers[type] = hHandlers[type] || []).push(fn) };
globalThis.Image = function(){ return hNothing };
const hStore = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in hStore ? hStore[k] : null),
  setItem: (k, v) => { hStore[k] = String(v) },
  removeItem: (k) => { delete hStore[k] } };
/* What the page asked the device for, in order. A missing vibrate is the
   normal case on most hardware; this records the call, not the buzz. */
const hSent = [];
Object.defineProperty(globalThis, 'navigator', { configurable: true, writable: true,
  value: { vibrate: (pattern) => { hSent.push(pattern); return true } } });
globalThis.document = { readyState: 'complete',
  createElement: () => hNothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {}, addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => hNothing }) };
globalThis.location = { reload: () => {} };
let hQueued = null;
globalThis.requestAnimationFrame = (fn) => { hQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
let hFrame = 0;
function hRun(n){ for (let i = 0; i < n && hQueued; i++) {
  const fn = hQueued; hQueued = null; hFrame += 1; fn(hFrame * (50 / 3)) } }
function hKey(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (hHandlers[type] || []).forEach(fn => fn(e)) }
hKey('keydown', ' '); hKey('keyup', ' ');
hRun(4);
const armed = hapticFacts();
/* Ten failure beats back to back: the window gate is the whole reason this
   is safe to ship, so it has to be pushed rather than described. */
const burstSent = [];
for (let i = 0; i < 10; i++) { failBeat(10, 10); burstSent.push(hSent.length) }
const afterBurst = hapticFacts();
/* ...and then the round, *played* out to its own confirmation. The keypress
   that opens a round is not playing it (C-1123), so a probe that only
   pressed Space would measure an untouched round - which banks nothing and
   is meant to stay silent in the hand too. PLAY_INPUT holds a real control
   down so the round is one somebody played. */
if (PLAY_INPUT) { hKey('keydown', 'ArrowLeft') }
hRun(FRAMES_INPUT);
const end = hapticFacts();
console.log(JSON.stringify({
  reduced: REDUCED, on: armed.on, armedFired: armed.fired,
  burstFired: afterBurst.fired, burstSteps: burstSent,
  endFired: end.fired, max: end.max, sent: hSent,
  patterns: end.sent,
  roundDone: (function(){ try { return roundFacts().done } catch (e) { return null } })(),
  banked: (function(){ try { return roundFacts().score } catch (e) { return null } })(),
}));
"""


def page_probe_source(
    script: str,
    *,
    reduced: bool = False,
    stored: dict | None = None,
    frames: int = 4200,
    play: bool = True,
) -> str:
    """Drive a whole page with the vibrator recorded and the switch settable.

    ``play`` holds a control down for the round, which is what makes the
    round a played one; without it the round banks nothing and the
    confirmation is correctly silent.
    """

    import json as _json

    packed = {
        key: (value if isinstance(value, str) else _json.dumps(value))
        for key, value in (stored or {}).items()
    }
    return (
        PAGE_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("PLAY_INPUT", "true" if play else "false")
        .replace("STORED_INPUT", _json.dumps(packed))
    )


__all__ = [
    "FAIL_HITSTOP",
    "FAIL_PARTICLES",
    "FAIL_SHAKE",
    "JUICE_PREAMBLE",
    "PREAMBLE_NAMES",
    "PROBE",
    "PAGE_PROBE",
    "WIN_HITSTOP",
    "WIN_PARTICLES",
    "WIN_SHAKE",
    "page_probe_source",
    "probe_source",
]


#: Runs a scoring template and writes down, frame by frame, what the score
#: was and what was painted over the game. The two together are the whole
#: claim: a 「+N」 that does not match what went in is the page lying about
#: the one thing the player is trying to learn.
POP_PROBE = """
const popNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : popNothing),
  apply: () => popNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT,
  addEventListener(){}, addListener(){} });
let popClock = 0;
globalThis.performance = { now: () => popClock };
const popKeys = [], popPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') popKeys.push(fn) };
globalThis.Image = function(){ return popNothing };
const popStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in popStore ? popStore[k] : null),
  setItem: (k, v) => { popStore[k] = String(v) }, removeItem: (k) => { delete popStore[k] } };
globalThis.location = { reload: () => {} };
globalThis.KeyboardEvent = function(type, init){ return Object.assign({ type: type }, init) };
globalThis.dispatchEvent = (ev) => { if (ev && ev.type === 'keydown') {
  popKeys.forEach(fn => fn(ev)) } return true };
let popPaint = [];
const popEl = { width: 720, height: 320, style: {}, textContent: '', attrs: {}, handlers: {},
  addEventListener: (name, fn) => { if (name === 'pointerdown') popPointers.push(fn) },
  setAttribute(){}, getAttribute(){ return null }, blur(){},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    fillText: (s, x, y) => { popPaint.push({ s: String(s),
      x: Math.round(Number(x) || 0), y: Math.round(Number(y) || 0) }) },
    fillRect: () => {} }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : popNothing)),
    set: () => true }) };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => popEl, querySelector: () => null, getElementById: () => popEl };
let popQueued = null;
globalThis.requestAnimationFrame = (fn) => { popQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
const popHold = HOLD_INPUT;
function popStepFrame(){ if (!popQueued) return null;
  const fn = popQueued; popQueued = null; popPaint = []; popClock += 50 / 3; fn(popClock);
  /* Only the floats: 「+12」 and nothing else on the screen looks like it. */
  return popPaint.filter(op => /^\\+[0-9]+$/.test(op.s)) }
popStepFrame(); popStepFrame();
popKeys.forEach(fn => fn({ key: ' ', code: 'Space',
  preventDefault(){}, stopImmediatePropagation(){} }));
const seen = [];
/* Counted in frames the game actually advanced, not in frames handed to
   the browser. The juice kit freezes the loop for a few frames on a hit,
   and reduced motion switches that freeze off - so a fixed browser-frame
   budget quietly gives the two settings different numbers of game steps
   and different scores, with the decoration blamed for it. Measured: with
   scorePop disabled entirely, shooter still scored 49 against 45 that
   way. Holding the *game* steps equal is what makes the reduced run a
   control rather than a second experiment. */
let advanced = 0;
for (let f = 0; f < FRAMES_INPUT * 4 && advanced < FRAMES_INPUT; f++) {
  if (popHold) { popKeys.forEach(fn => fn({ key: popHold, code: popHold,
    preventDefault(){}, stopImmediatePropagation(){} })) }
  const painted = popStepFrame();
  if (painted === null) break;
  if (popPaint.length) { advanced++ }
  const facts = popFacts();
  let score = null;
  try { score = roundFacts().live } catch (e) {}
  seen.push({ score: score, live: facts.live, shown: facts.shown,
    /* Every fill on the frame, not only the floats. The juice kit freezes
       the whole loop on a hit, and a frozen frame paints nothing at all -
       the canvas keeps the previous picture. That is a different thing
       from a frame that redrew the game and left the floats off it. */
    all: popPaint.length,
    dropped: facts.dropped, total: facts.total,
    /* What the page is holding, beside what it actually put on the glass. */
    said: facts.said.slice(),
    painted: painted.map(op => op.s), at: painted.map(op => [op.x, op.y]) });
}
const end = popFacts();
/* No natural run scores fast enough to reach the cap, so it is asked
   directly: the page's own function, called more times than it will hold.
   Without this 条件② would be a number nobody had ever seen move. */
const stressBefore = popFacts();
for (let i = 0; i < STRESS_INPUT; i++) { scorePop(10, 10, 1) }
const stressAfter = popFacts();
const stressPainted = popStepFrame();
console.log(JSON.stringify({ frames: seen, end: end,
  max: end.max, reduced: end.reduced,
  stress: { asked: STRESS_INPUT, before: stressBefore, after: stressAfter,
    painted: (stressPainted || []).length } }));
"""


def pop_probe_source(
    script: str,
    *,
    reduced: bool = False,
    frames: int = 2400,
    hold: str = "",
    stress: int = 0,
) -> str:
    """The page's own script, wrapped so the scoring can be watched land."""

    return (
        POP_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("HOLD_INPUT", json.dumps(hold))
        .replace("STRESS_INPUT", str(int(stress)))
    )
