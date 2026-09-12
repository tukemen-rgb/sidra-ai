"""Shared pieces for the probes that drive real pages (C-1652, C-1656).

The pairing of a key with its code lives in :mod:`probekeys`, which C-1651
built for exactly that reason. This module used to define a second
``probeKey`` of its own - three arguments, dispatching as well as building
- behind the *same* injection token, so the one name meant two different
functions depending on which builder ran (C-1656). Nothing was broken by
it, because each probe was internally consistent, but swapping a builder
would have produced a probe that silently dispatched nothing: quieter than
a crash and harder to notice than the mistake C-1651 set out to stop.

So the branch is not redefined here. What this module adds is the part
``probekeys`` deliberately does not own: sending the event to the page's
listeners, and reading one frame's own camera kick.
"""

from __future__ import annotations

from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: A synthesised keyboard event, built the way the pages actually read it.
#: The templates are split: some test ``e.key``, some test ``e.code``, and
#: for the space bar those two differ (``' '`` against ``'Space'``). Any
#: probe that presses a key should embed this rather than hand-roll it.
#: Send a key to the page, built by the one function that knows how a
#: key pairs with its code (:data:`probekeys.KEY_EVENT_JS`). The name is
#: deliberately NOT ``probeKey``: that name belongs to the shared branch,
#: and two functions answering to it was the whole of C-1656.
#:
#: ``stopImmediatePropagation`` is honoured because the templates' own
#: listeners call it, and a probe that kept dispatching past it would be
#: feeding the page events a browser would have withheld.
PROBE_SEND = (
    KEY_EVENT_JS
    + """
function probeSend(type, k, handlers){
  let stopped = false;
  const e = probeKey(k);
  const guard = e.stopImmediatePropagation;
  e.stopImmediatePropagation = function(){ stopped = true; return guard.call(e) };
  for (const fn of (handlers[type] || [])) { fn(e); if (stopped) break }
  return e }
"""
)


#: Read one frame's own camera kick, not the history of every kick before
#: it (C-1648). ``shake()`` keeps ``Math.max`` and decays it by 0.78 each
#: frame, so a heavy event a few frames back sits on top of a light one and
#: inverts the ladder. Clearing the accumulator before each frame is the
#: probe's own view; the page is untouched.
PROBE_SHAKE = """
function probeKick(step){
  SHAKE = 0;
  step();
  return shakeAmount() }
"""


#: A stand-in AudioContext that keeps the pan of every sound it is asked
#: to place (§28, C-1653). The pages put an event's normalised x on a
#: StereoPannerNode; this is the only way to read back where the ear was
#: told the thing happened, and it is the same shape the pan contract has
#: used since C-1394.
PROBE_EARS = """
const pans = [];
function Recorder(){ this.currentTime = 0; this.state = 'running';
  this.destination = { kind: 'dest' }; this.sampleRate = 44100;
  this.resume = function(){} }
Recorder.prototype.createGain = function(){ return {
  gain: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  connect(){} } };
Recorder.prototype.createOscillator = function(){ return { type: '',
  frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  setPeriodicWave(){}, connect(){}, start(){}, stop(){} } };
Recorder.prototype.createPeriodicWave = function(){ return {} };
Recorder.prototype.createBuffer = function(ch, len){ return {
  getChannelData: () => new Float32Array(len) } };
Recorder.prototype.createBufferSource = function(){ return { buffer: null,
  connect(){}, start(){}, stop(){} } };
Recorder.prototype.createBiquadFilter = function(){ return { type: '',
  frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  connect(){} } };
Recorder.prototype.createStereoPanner = function(){ return {
  pan: { setValueAtTime(v){ pans.push(v) } }, connect(){} } };
globalThis.window = { AudioContext: Recorder };
"""

#: Watch both channels of one event: where the ear was told it happened
#: (the pan the page put on the sound) and where the light was actually
#: drawn (the x the page handed burst). Both are the page's own runtime
#: calls. Install after the page's script has been defined.
PROBE_EYES = """
let heard = [], seen = [], EE_FRAME = 0;
function eeTick(){ EE_FRAME++ }
(function(){
  const realSfx = sfx, realBurst = burst;
  sfx = function(name, pitch, at){
    const was = pans.length;
    const out = realSfx.apply(this, arguments);
    heard.push({ name: String(name), frame: EE_FRAME,
      at: (typeof at === 'number' ? at : null),
      pan: pans.length > was ? pans[pans.length - 1] : null });
    return out };
  burst = function(x){ seen.push({ x: x, frame: EE_FRAME });
    return realBurst.apply(this, arguments) };
})();
/* The two channels do not always speak the same coordinates, and that is
   not a fault. The platformer pans camera-relative while its light is
   drawn in world x; the marble pans by LANE because the projection at
   gate range magnifies screen x so far that a wide gate would saturate
   the panner (the page says so in a comment). So a probe hands in the
   map from a burst x to the pan's own space, and where no such map
   exists the two are only asked to agree on the SIDE - which is the part
   §28 actually cares about: which way the event was. */
function earEye(name, width, toNorm){
  const ear = heard.filter(h => h.name === name && h.at !== null).pop();
  if (!ear) return null;
  /* Only light drawn on the same frame as the sound can be the sound's
     own (C-1653). Without this the nearest burst anywhere in the whole
     run gets matched, which made a respawn 1900px from its own picture
     look like a near miss. */
  const near = seen.filter(s => Math.abs(s.frame - ear.frame) <= 1);
  if (!near.length) return { name: name, earNorm: ear.at, pan: ear.pan,
    eyeNorm: null, apartPx: null, sameSide: false, mapped: !!toNorm,
    litNothing: true };
  const norm = toNorm || function(x){ return x / width };
  let eyeNorm = norm(near[0].x);
  for (const s of near) {
    const n = norm(s.x);
    if (Math.abs(n - ear.at) < Math.abs(eyeNorm - ear.at)) eyeNorm = n }
  const side = function(v){ return v < 0.45 ? -1 : (v > 0.55 ? 1 : 0) };
  return { name: name, earNorm: ear.at, pan: ear.pan, eyeNorm: eyeNorm,
    apartPx: Math.abs(eyeNorm - ear.at) * width,
    sameSide: side(ear.at) === side(eyeNorm),
    mapped: !!toNorm, litNothing: false } }
/* Some events do not paint one dot. The puzzle's clear rings at the
   CENTRE of the group it cleared and lights every tile in it, which is
   the design (C-1418: a big clear's number appears where the big clear
   was), so the honest question is whether the ear points INSIDE what the
   eye painted. For a single-burst event the span collapses and this is
   the same as coincidence. */
function earInSpan(name, width, toNorm){
  const ear = heard.filter(h => h.name === name && h.at !== null).pop();
  if (!ear) return null;
  const near = seen.filter(s => Math.abs(s.frame - ear.frame) <= 1);
  if (!near.length) return { name: name, earNorm: ear.at, litNothing: true,
    inside: false, lo: null, hi: null };
  const norm = toNorm || function(x){ return x / width };
  const xs = near.map(function(s){ return norm(s.x) });
  const lo = Math.min.apply(null, xs), hi = Math.max.apply(null, xs);
  /* Half a cell of slack at each end: the burst sits at a tile's centre,
     so a two-tile clear's centroid lands between two dots rather than on
     one, and the span's own ends are centres too. */
  const pad = 24 / width;
  return { name: name, earNorm: ear.at, lo: lo, hi: hi, lit: near.length,
    inside: ear.at >= lo - pad && ear.at <= hi + pad, litNothing: false } }
"""

#: One thumb, never two (§8 事実 5, C-1702).
#:
#: Voodoo's shipping question is whether the game works one-handed on a
#: crowded train, and on a phone the pad is a rectangle drawn inside the
#: canvas - so "two inputs at once" means two thumbs. This driver makes
#: that impossible by construction: every press releases whatever was
#: held first, so at no instant is more than one key down. A template
#: that needs a direction held *while* an action fires cannot make
#: progress under it, which is the whole point.
PROBE_THUMB = """
let thumbDown = null;
function thumbEvent(type, k){
  const e = probeKey(k);
  e.target = { tagName: 'CANVAS' };
  (handlers[type] || []).forEach(fn => fn(e));
}
/* Hold one key - letting go of any other first, so the hand only ever
   has one finger on the pad. */
function hold(k, frames){
  if (thumbDown !== null && thumbDown !== k) { thumbEvent('keyup', thumbDown); thumbDown = null }
  if (thumbDown !== k) { thumbEvent('keydown', k); thumbDown = k }
  run(frames);
}
function release(){
  if (thumbDown !== null) { thumbEvent('keyup', thumbDown); thumbDown = null } }
/* Press, then let go, then let the world move on its own. */
function tap(k, frames){ hold(k, frames); release(); run(1) }
function thumbHeld(){ return thumbDown }
"""

__all__ = [
    "PROBE_SEND",
    "PROBE_SHAKE",
    "PROBE_EARS",
    "PROBE_EYES",
    "PROBE_THUMB",
]
