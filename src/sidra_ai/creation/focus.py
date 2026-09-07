"""Held input lets go when the page loses focus (§22, C-1373).

A keyup released in another window never arrives: the browser stops
delivering key events the moment focus leaves, so a key held across
alt-tab (or an incoming call, or the home screen) stays pressed in every
flag a template keeps - and every template keeps one, because §12 事実 3
made held movement a flag read each frame. The player comes back to a
hero running on their own. The engine-level report of exactly this
(Emscripten #5122) was closed wontfix: releasing input on focus loss is
the application's job, and this preamble is that job done once for all
ten templates.

Mechanism: installed right after the remap wrapper, so it wraps remap's
``addEventListener`` and therefore hears keys in the spelling the game
reads (already translated). It keeps the set of keys currently down and
the list of registered keyup handlers; on ``blur``, ``pagehide``, or the
document going hidden it feeds one synthetic keyup per held key into
those same handlers - the normal wiring, not a reach into any template's
private ``keys`` object. §22's two signals both matter: blur fires when
focus leaves even though the page may stay visible (and unfocused pages
get no key events, so input must release), while hidden covers the tab
switch and the phone's home screen.

The round clock's absence forgiveness (C-1450) protects the time; this
protects the controls. Both exist because a player who steps away should
find the game where they left it, not somewhere it walked to alone.
"""

from __future__ import annotations

#: Names this preamble introduces, for the vocabulary test.
PREAMBLE_NAMES: tuple[str, ...] = (
    "focusRelease",
    "focusFacts",
)

FOCUS_PREAMBLE = """
/* --- focus loss releases held input (§22, C-1373) --------------------
   A keyup released in another window never arrives, so the held-key
   flags templates keep (§12 事実 3) stay pressed for a player who has
   left. Wrapped over the remap wrapper: what is tracked here is the key
   the game reads, and release feeds synthetic keyups through the same
   registered handlers, so no template's private state is touched. */
let FOCUS_DOWN={},FOCUS_KEYUPS=[],FOCUS_RELEASES=0;
const FOCUS_AEL=addEventListener;
globalThis.addEventListener=function(type,fn,opt){
  if(type!=='keydown'&&type!=='keyup')return FOCUS_AEL(type,fn,opt);
  if(type==='keyup')FOCUS_KEYUPS.push(fn);
  return FOCUS_AEL(type,function(e){
    if(e&&typeof e.key==='string'){
      if(type==='keydown'){FOCUS_DOWN[e.key]=true}
      else{delete FOCUS_DOWN[e.key]}}
    fn(e)},opt)};
function focusRelease(){
  const held=Object.keys(FOCUS_DOWN);FOCUS_DOWN={};
  if(!held.length)return 0;
  FOCUS_RELEASES++;
  held.forEach(function(k){
    const e={key:k,code:k===' '?'Space':(k.length===1?'Key'+k.toUpperCase():k),
      preventDefault:function(){},stopImmediatePropagation:function(){}};
    FOCUS_KEYUPS.forEach(function(fn){try{fn(e)}catch(err){}})});
  return held.length}
/* Both of §22's signals, because they cover different exits: blur fires
   when focus leaves even if the page stays visible (no key events reach
   an unfocused page), hidden covers the tab switch and the phone's home
   screen, pagehide the navigation away. */
FOCUS_AEL('blur',function(){focusRelease()});
FOCUS_AEL('pagehide',function(){focusRelease()});
try{if(typeof document!=='undefined'&&document.addEventListener){
  document.addEventListener('visibilitychange',function(){
    if(document.hidden)focusRelease()})}}catch(e){}
function focusFacts(){return {held:Object.keys(FOCUS_DOWN),
  releases:FOCUS_RELEASES}}
"""

#: The page driven in node: a held key moves the game, focus loss lets it
#: go, and the game stands still afterwards - read off the running
#: template, not the source. ``FACTS_PLACEHOLDER`` is a JS expression for
#: the one number that moves while the key is held (the hero's x).
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.document = {
  hidden: false,
  addEventListener: (type, fn) => { (handlers['doc:' + type] = handlers['doc:' + type] || []).push(fn) },
  getElementById: () => ({
    width: 720, height: 320, style: {}, addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
/* Past the briefing, and let the board settle. */
ev('keydown', ' '); ev('keyup', ' ');
run(30);
/* Hold the key - keydown with no keyup, exactly what alt-tab leaves. */
ev('keydown', 'HOLD_PLACEHOLDER');
const x0 = FACTS_PLACEHOLDER;
run(8);
const x1 = FACTS_PLACEHOLDER;
const heldBefore = focusFacts().held.slice();
/* The player leaves. */
if ('SIGNAL_PLACEHOLDER' === 'hidden') {
  document.hidden = true;
  (handlers['doc:visibilitychange'] || []).forEach(fn => fn({}));
  document.hidden = false;
} else {
  (handlers['SIGNAL_PLACEHOLDER'] || []).forEach(fn => fn({}));
}
const heldAfter = focusFacts().held.slice();
const x2 = FACTS_PLACEHOLDER;
run(30);
const x3 = FACTS_PLACEHOLDER;
console.log(JSON.stringify({
  moved: x1 - x0, heldBefore: heldBefore, heldAfter: heldAfter,
  drift: x3 - x2, releases: focusFacts().releases,
}));
"""


def probe_source(script: str, *, hold: str, facts: str, signal: str) -> str:
    """The page's own script, wrapped so a focus loss can be watched.

    ``hold`` is the key to press and abandon, ``facts`` a JS expression
    for the coordinate that key moves, ``signal`` one of ``blur``,
    ``pagehide`` or ``hidden``.
    """

    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("HOLD_PLACEHOLDER", hold)
        .replace("FACTS_PLACEHOLDER", facts)
        .replace("SIGNAL_PLACEHOLDER", signal)
    )


__all__ = [
    "FOCUS_PREAMBLE",
    "PREAMBLE_NAMES",
    "PROBE",
    "probe_source",
]
