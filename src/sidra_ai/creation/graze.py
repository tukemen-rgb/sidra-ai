"""An optional risk: fly close to what would kill you, and get paid.

§13 事実 1: nothing in the product is a danger you are allowed to decline.
Every hazard is simply to be avoided, so the only choice a player makes is
whether to play well, not whether to gamble. Pac-Man's blue ghosts are the
shape of the missing thing - a threat that briefly becomes an opportunity,
which nobody has to take.

Wired into ``shooter``. **The backlog entry says 敵弾 (enemy bullets) and
the shooter has none** - it has descending hulls that kill on contact, and
that is what the graze band sits outside of. Adding a bullet type to graze
instead would have added a hazard, and the entry's own constraint is that
the difficulty does not move.

The rules that keep this a risk rather than a farm:

* **Once per hazard.** Sitting beside a foe and being paid every frame is
  an exploit, not a decision, so each hull can be grazed a single time.
* **The band is outside the kill radius, and the kill radius does not
  move.** A graze is strictly harder than not grazing. Nothing about the
  fight is easier because this exists.
* **The reward is points and nothing else.** No shield, no slow, no
  second life - anything else would make declining the risk a mistake.
* **It pays on a run, not per graze.** One brush is worth nothing; three
  in a row are worth a point. That is what makes taking a hit cost
  something beyond the hull it costs already.
* **A hit takes the run**, including the part already earned toward the
  next point. The banked points stay banked - losing those would be a
  punishment for having played well earlier.
"""

from __future__ import annotations

import json

from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: Wired here first, for the same reason the combo ladder was: one running
#: page can be judged, nine cannot be judged at once.
#:
#: kaiju is the second (C-1419), and the entry that asked for it was wrong
#: about what it would be wired to - as this table's own note was. Both
#: said 「拳」: the boss has no fists. It opens cracks in the ground, and
#: what a player stands near is a crack whose radius grows as it widens.
#: That is the hazard the band went outside of. The same correction the
#: docstring above records for the shooter's 敵弾.
GRAZE_TEMPLATES: tuple[str, ...] = ("shooter", "kaiju")

#: Why each of the others is not wired. "Nothing to graze" and "not yet"
#: are different answers, and only the second is a backlog item.
GRAZE_UNWIRED: dict[str, str] = {
    # Measured, not reasoned about (C-1446, the same discipline C-1429
    # forced). This entry used to say "a parry window already fills this
    # role", and duel has no parry: the word appears nowhere in the
    # template, and nothing in it blocks or catches a shot. What it does
    # have is a telegraph. The enemy's aim is shown for AIM_LOCK frames
    # and the shot lands in that lane, so the answer is to be somewhere
    # else by the time it fires - driven on the real page: 18 frames of
    # warning, step to another lane and hp goes 3 -> 3, stay in it and
    # hp goes 3 -> 2.
    #
    # So the judgement the entry was making survives, and its reason
    # changes: the risk window is already there, and a graze band would
    # pay a second time for the same instant of standing in the beam's
    # lane. That is the decision, and it is not one to take here.
    "duel": "it already has a risk window under another name: the enemy's aim shows "
    "for AIM_LOCK (18) frames and stepping out of that lane avoids the shot - "
    "a band would pay a second time for the same instant; two risk layers needs "
    "a decision",
    # Measured, not reasoned about (C-1429). The worry this entry used
    # to record - "a band would pay continuously" - is not what the
    # page does: the pass is evaluated at the single instant an
    # obstacle goes behind the car, and the obstacle is dropped from
    # the list on that same frame, so one obstacle is worth exactly one
    # evaluation however long the car rode alongside it. The band even
    # starts where the hitbox ends (26-46px), which is this preamble's
    # own rule. What racing lacks is not a band; it already has one
    # under another name, and creation_race_slipstream already checks
    # the four things a graze judge would.
    "racing": "it already has this: the C-1325 slipstream pays once per obstacle shaved, "
    "in pace rather than points - a second band would pay twice for one act",
    "marble": "the drop is the hazard and its edge is the course itself",
    "platformer": "the gaps do not move, so a near-miss is a fixed property of the level rather than a choice",
    "catch": "nothing there can hurt you; a missed item is a lost point, not a danger",
    "fishing": "the band is the whole mechanic already",
    "puzzle": "no hazard and no position",
    "adventure": "the rooms hold no moving threat",
}

#: How far outside the kill radius still counts, in canvas pixels. The
#: shooter's kill radius is about 26px, so this is a ribbon roughly half
#: that wide - close enough that reaching it is a decision and not an
#: accident, wide enough to be reachable at the speed the hulls fall.
GRAZE_BAND = 14

#: Brushes in a row that make a point. One is luck; three is a run you
#: chose to keep going, which is the thing a hit can take away.
GRAZE_RUN = 3

#: Names the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "grazeNear",
    "grazeStruck",
    "grazeLost",
    "grazeReset",
    "grazeFacts",
)

GRAZE_PREAMBLE = """
/* --- a danger you may decline (§13 事実 1) -------------------------- */
const GRAZE_BAND=GRAZE_BAND_TOKEN,GRAZE_NEED=GRAZE_NEED_TOKEN;
let GRAZE_SEEN=0,GRAZE_STREAK=0,GRAZE_PAID=0;
/* Every brush, with the distance and kill radius the page used to judge
   it. A probe cannot measure this from outside: the hulls move inside the
   frame, so the gap an onlooker reads before the frame is not the gap the
   collision check saw - an early version of the judge read distances of
   40-44 for grazes the page had correctly taken at under 40. Capped so a
   long round cannot grow it without bound. */
const GRAZE_LOG=[];
/* And every hull that actually landed, at the gap it landed from. This is
   the only honest way to ask whether the collision moved: the radius a
   page *reports* is a number recomputed beside the check, and a check that
   had drifted would keep reporting the old one. Shrinking the kill radius
   by a band's width passed a judge that read the reported number. */
const GRAZE_HIT=[];
function grazeFacts(){return {seen:GRAZE_SEEN,run:GRAZE_STREAK,
  paid:GRAZE_PAID,band:GRAZE_BAND,need:GRAZE_NEED,
  at:GRAZE_LOG.slice(0,200),struck:GRAZE_HIT.slice(0,200)}}
function grazeStruck(dist,kill){if(GRAZE_HIT.length<200){
  GRAZE_HIT.push([Math.round(dist*100)/100,Math.round(kill*100)/100])}}
function grazeReset(){GRAZE_SEEN=0;GRAZE_STREAK=0;GRAZE_PAID=0;
  GRAZE_LOG.length=0;GRAZE_HIT.length=0}
/* The banked points stay banked: losing those would punish a player for
   having played well earlier in the same round. */
function grazeLost(){GRAZE_STREAK=0}
/* ``kill`` is the radius that would have ended it - passed in rather than
   recomputed, so this can never disagree with the collision the template
   actually runs. Counted once per hazard: being paid every frame for
   standing still is a farm, not a risk. */
function grazeNear(hazard,kill,dist,x,y){
  if(!hazard||hazard.grazed)return false;
  if(!(dist>kill&&dist<=kill+GRAZE_BAND))return false;
  hazard.grazed=true;GRAZE_SEEN++;GRAZE_STREAK++;
  if(GRAZE_LOG.length<200){GRAZE_LOG.push([Math.round(dist*100)/100,
    Math.round(kill*100)/100])}
  /* The pass is heard where it happens (§2, C-1364): thin air - white
     noise through a RISING high-pass, quiet, once per hazard. The sound
     stays under reduced motion (information); the sparks below do not. */
  try{sfx('graze')}catch(e){}
  try{if(typeof REDUCED==='undefined'||!REDUCED){burst(x,y,4,'ACCENT_JUICE')}}catch(e){}
  if(GRAZE_STREAK>=GRAZE_NEED){GRAZE_STREAK=0;GRAZE_PAID++;
    /* The point is said where the risk was taken (C-1418). This one was
       the most opaque payment on the page: a near miss pays through
       grazeFacts().paid rather than through the template's own `score`,
       so the total moved and nothing on the screen said why. Guarded
       because only two templates carry the graze preamble at all. */
    try{scorePop(x,y,1)}catch(e){}
    try{sfx('gem')}catch(e){}}
  return true}
"""


def preamble_for(template: str) -> str:
    """The rule, for the templates that have a hazard worth brushing."""

    if template not in GRAZE_TEMPLATES:
        return ""
    return GRAZE_PREAMBLE.replace("GRAZE_BAND_TOKEN", str(GRAZE_BAND)).replace(
        "GRAZE_NEED_TOKEN", str(GRAZE_RUN)
    )


#: The probe. Flies the real generated fight three ways - hugging the
#: nearest hull, keeping clear of it, and steering into it - so the claim
#: is read off a page that played rather than off this source.
PROBE = KEY_EVENT_JS + """
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
let bursts = 0;
const realBurst = burst;
burst = (...a) => { bursts++; return realBurst(...a) };
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) {
  const fn = queued; queued = null; fn((F++) * 16) } }
function key(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e)) }
key('keydown', ' '); key('keyup', ' ');
run(2);
/* The hull the ship would meet first, and the radius that would end it.
   Read off the page's own state, so the probe cannot drift from the
   collision the template runs. */
function nearest(){ let best = null, bd = 1e9;
  foes.forEach(f => { if (f.hp <= 0) return;
    const d = Math.hypot(f.x - ship.x, f.y - ship.y);
    if (d < bd) { bd = d; best = f } });
  return best ? { foe: best, dist: bd, kill: best.r + SHIP * 0.6 } : null }
/* MODE_INPUT: 'hug' rides the edge of the band, 'clear' holds the corner,
   and 'crash' walks into the hull on purpose. Steering is done by moving
   the ship the way a held arrow key would, one step at a time.

   The modes are how the page is *driven*; they are not the evidence. A
   formation fills the width, so "keeping away" from the nearest hull can
   park the ship beside the next one - a run labelled 'clear' grazed seven
   times and lost two hulls, so no mode proves "far away earns nothing".
   The proof is ``grazeFacts().at``, which is the page's own record of the
   gap and the kill radius at each brush. Measuring it from out here read
   the hulls' positions *before* the frame moved them, and reported grazes
   at 40-44 against a band that ends at 40.2 - the geometry was right and
   the instrument was wrong. */
const MODE = MODE_INPUT;
const timeline = [];
let lastSeen = 0, lastHp = null;
for (let f = 0; f < FRAMES_INPUT && shooterFacts().state === 'play'; f++) {
  const near = nearest();
  if (near) {
    const want = MODE === 'clear' ? 1e6
      : MODE === 'crash' ? 0
      : near.kill + GRAZE_BAND * 0.5;
    /* Aim the horizontal gap so the straight-line distance lands where the
       mode wants it; the ship only moves in x. */
    const dy = Math.abs(near.foe.y - ship.y);
    const dx = want > dy ? Math.sqrt(want * want - dy * dy) : 0;
    const side = near.foe.x >= ship.x ? -1 : 1;
    const target = Math.max(22, Math.min(720 - 22, near.foe.x + side * dx));
    ship.x += Math.max(-4, Math.min(4, target - ship.x));
  }
  run(1);
  const now = shooterFacts();
  const hit = lastHp !== null && now.hp < lastHp;
  if (now.graze.seen !== lastSeen || hit) {
    timeline.push({ at: f, seen: now.graze.seen, run: now.graze.run,
      paid: now.graze.paid, hp: now.hp, score: now.score, hit: hit,
      hud: drawn.filter(t => t.indexOf('かすり') === 0)[0] || null });
    lastSeen = now.graze.seen }
  lastHp = now.hp;
  drawn = [] }
const end = shooterFacts();
console.log(JSON.stringify({ timeline, graze: end.graze, kill: end.kill,
  band: GRAZE_BAND, score: end.score, hp: end.hp, t: end.t,
  roundScore: roundScore(), bursts }));
"""


def probe_source(
    script: str, *, mode: str = "hug", frames: int = 1800, reduced: bool = False
) -> str:
    """Fly the fight one of three ways: hugging, clear, or into the hull."""

    if mode not in ("hug", "clear", "crash"):
        raise ValueError(f"unknown flight mode: {mode}")
    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("MODE_INPUT", json.dumps(mode))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
    )


#: The pass, as heard (§2, C-1364). A recording AudioContext with a
#: type-aware filter log drives the built page's own ``grazeNear`` twice
#: with two hazards inside the band, then again with a hazard already
#: grazed and once with M held: the whoosh is white noise through a
#: RISING high-pass, once per hazard, silent under the mute - and the
#: hurt keeps its falling low-pass, which is the axis's other character.
WHOOSH_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
let rnd = 2463534242;
Math.random = () => { rnd ^= rnd << 13; rnd ^= rnd >>> 17; rnd ^= rnd << 5;
  return ((rnd >>> 0) % 100000) / 100000 };
const nodes = [];
const filtFreqs = [];
function Recorder(){ this.state='running'; this.currentTime=0; this.destination={};
  this.sampleRate=44100 }
Recorder.prototype.createPeriodicWave = function(){ return {} };
Recorder.prototype.createOscillator = function(){
  return { type:'', frequency:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} },
           setPeriodicWave(){}, connect(){ nodes.push('oscillator') },
           start(){}, stop(){} } };
Recorder.prototype.createBuffer = function(ch, len){
  return { getChannelData: () => new Float32Array(len) } };
Recorder.prototype.createBufferSource = function(){
  return { buffer:null, start(){}, stop(){},
    connect(t){ nodes.push(t && t.kind === 'filter'
      ? 'noise->' + (t.type || 'lowpass') : 'noise->direct') } } };
Recorder.prototype.createBiquadFilter = function(){
  const f = { kind:'filter', type:'',
    frequency:{ setValueAtTime(v){ filtFreqs.push(v) },
                exponentialRampToValueAtTime(v){ filtFreqs.push(v) } },
    connect(){ nodes.push((f.type || 'lowpass') + '->out') } };
  return f };
Recorder.prototype.createGain = function(){
  return { gain:{ value:0, setValueAtTime(){}, exponentialRampToValueAtTime(){} },
    connect(){} } };
globalThis.window = { AudioContext: Recorder };
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
const keyHandlers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') keyHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
function press(k){ keyHandlers.forEach(fn => fn(probeKey(k))) }
press(' ');
run(2);
function whoosh(fn){ nodes.length = 0; filtFreqs.length = 0; fn();
  return { nodes: nodes.slice(), freqs: filtFreqs.slice() } }
const kill = 20, dist = kill + GRAZE_BAND * 0.5;
const first = whoosh(() => grazeNear({}, kill, dist, 10, 10));
const second = whoosh(() => grazeNear({}, kill, dist, 10, 10));
const seen = { grazed: true };
const repeat = whoosh(() => grazeNear(seen, kill, dist, 10, 10));
press('m');
const muted = whoosh(() => grazeNear({}, kill, dist, 10, 10));
press('m');
const hurt = whoosh(() => sfx('hurt'));
console.log(JSON.stringify({ first: first, second: second,
  repeatNodes: repeat.nodes.length, mutedNodes: muted.nodes.length,
  hurtNodes: hurt.nodes,
  table: (typeof SFX_TABLE !== 'undefined' && SFX_TABLE.graze) ? SFX_TABLE.graze : null }));
"""


def whoosh_probe(script: str) -> str:
    """One built page, its near miss listened to four ways."""

    return WHOOSH_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "GRAZE_BAND",
    "GRAZE_PREAMBLE",
    "WHOOSH_PROBE",
    "whoosh_probe",
    "GRAZE_RUN",
    "GRAZE_TEMPLATES",
    "GRAZE_UNWIRED",
    "PREAMBLE_NAMES",
    "PROBE",
    "preamble_for",
    "probe_source",
]
