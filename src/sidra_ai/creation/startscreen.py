"""A title screen, so nobody is playing before they have read anything.

Every template started the moment the page loaded. On a desktop that costs a
few seconds of confusion; on a phone the instructions sit below the fold, so
the player never sees them at all and the first thing that happens is losing
a life. It also meant the first sound arrived with no user gesture behind it,
which browsers refuse - the audio unlocked on some later keypress, or never.

One press fixes all three: it is the gesture that unlocks the AudioContext,
the moment the instructions have been on screen, and the start of the game.

The mechanism is the one the other shared preambles use - wrap
``requestAnimationFrame`` once - with one ordering fact behind it. Each
wrapper's own work runs *after* the wrapper installed later, because later
wrappers end up nested inside. So the gate is installed **first**, which puts
its overlay on top of the pad and the particles rather than under them. The
same fact means the juice preamble's particles draw over the touch pad; that
is fine, and it is the opposite of what C-1020's note claimed.

While the gate is closed the template's own callback is never called - the
game cannot advance a frame it has not been given - and the loop keeps
re-scheduling itself, exactly as the hitstop does.
"""

from __future__ import annotations

#: What the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = ("gateState", "gateFrames")

GATE_PREAMBLE = """
/* --- start screen and pause (installed first: its overlay draws last) --- */
const GCV=document.getElementById('stage');
const GTITLE=TITLE_TOKEN,GHOW=HOWTO_TOKEN;
let GATE='title',GATE_RAN=0;
function gateState(){return GATE}
function gateFrames(){return GATE_RAN}
function gateStart(){if(GATE==='playing')return;
  /* The press that starts the game is the user gesture the AudioContext has
     been waiting for; a game whose first sound is silent taught the player
     it has none. */
  GATE='playing';try{sfx('step')}catch(e){}}
function gateTogglePause(){if(GATE==='title')return;
  GATE=GATE==='paused'?'playing':'paused'}
addEventListener('keydown',e=>{
  if(e.key==='p'||e.key==='P'){e.preventDefault();e.stopImmediatePropagation();
    gateTogglePause();return}
  if(GATE!=='playing'){e.preventDefault();e.stopImmediatePropagation();
    gateStart()}},true);
if(GCV){GCV.addEventListener('pointerdown',e=>{
  if(GATE!=='playing'){e.preventDefault();e.stopImmediatePropagation();
    gateStart()}},true)}
function gateWrap(text,limit){const out=[];let line='';
  for(const ch of text){line+=ch;
    if(line.length>=limit){out.push(line);line=''}}
  if(line)out.push(line);return out}
function drawGate(){if(!GCV||GATE==='playing')return;
  const c=GCV.getContext('2d'),W=GCV.width,H=GCV.height;
  c.save();
  c.fillStyle=GATE==='title'?'SURFACE_TOKEN':'#05070fcc';
  c.fillRect(0,0,W,H);
  c.fillStyle='#dfe7f5';c.textAlign='center';
  c.font='22px ui-monospace,monospace';
  c.fillText(GATE==='title'?GTITLE:'一時停止',W/2,H/2-54);
  c.font='13px ui-monospace,monospace';
  if(GATE==='title'){
    gateWrap(GHOW,34).forEach((line,i)=>{c.fillText(line,W/2,H/2-18+i*20)})}
  c.font='15px ui-monospace,monospace';
  c.fillText(GATE==='title'?'タップ / SPACE ではじめる':'タップ / SPACE でつづける',
    W/2,H-46);
  c.font='12px ui-monospace,monospace';
  c.fillStyle='#9fb0c8';
  c.fillText('P で一時停止  /  M で消音',W/2,H-24);
  c.textAlign='left';c.restore()}
const GATE_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return GATE_RAF(function tick(t){
    /* Closed: the template never gets the frame, and the loop stays alive
       so one press can hand it back. */
    if(GATE!=='playing'){drawGate();GATE_RAF(tick);return}
    fn(t);GATE_RAN++})};
"""

#: Drives a generated page in node: hold the gate shut, count frames, press
#: start, count again. Recording the listeners is the whole point - a stubbed
#: ``addEventListener`` that drops them would make every page look gated.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [];
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
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
run(10);
const before = gateFrames(), stateBefore = gateState();
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(10);
console.log(JSON.stringify({
  stateBefore: stateBefore, framesBeforePress: before,
  stateAfter: gateState(), framesAfterPress: gateFrames(),
  handlers: keyHandlers.length,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the gate can be pressed in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = ["GATE_PREAMBLE", "PREAMBLE_NAMES", "PROBE", "probe_source"]
