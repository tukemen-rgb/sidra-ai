"""C-1416: the button that makes the game as big as the screen.

§18 事実 2: a phone gives about 40% of its screen to the URL bar and the
page's own margins, and the Fullscreen API takes it back - on current
Android Chrome/Firefox and on desktop, with iOS Safari only partly there
until 26.6. So the button is a progressive addition: present where the
browser says it will work, absent where it says it will not, and never the
thing a page needs in order to be playable.

The four rules from the item, and where each one lives:

1. Nobody is put into fullscreen. ``requestFullscreen`` is called from the
   click handler and from nowhere else - no load hook, no first frame, no
   "they pressed start so they must want it".
2. Feature-detected. The element is in the page but hidden, and the script
   shows it only when the browser reports the capability. A page whose
   script never ran shows no button rather than a dead one.
3. A refusal is not an error. ``requestFullscreen`` returns a promise that
   browsers reject freely - not from a user gesture, disallowed by
   permissions policy, already exiting. Every call site swallows it, and
   the instrument watches node's own unhandled-rejection channel to prove
   the swallow is real rather than a ``.catch`` that was written and then
   bypassed.
4. The orientation lock is optional and best-effort. It is attempted only
   once fullscreen is actually entered, and its failure - which is the
   normal case on desktop - is ignored the same way.

One thing that is not in the item and had to be: the button takes keyboard
focus when it is clicked, and the templates use SPACE. Left alone, a player
who taps 全画面 and then presses SPACE to shoot toggles fullscreen instead.
The handler blurs it, so the button is reachable by Tab and never sitting
under the game's own controls afterwards.
"""

from __future__ import annotations

#: The wrapper that goes fullscreen, the button that asks, and the canvas
#: they are both about. The wrapper rather than the canvas: a bare canvas
#: filling the screen would take the button with it and give no way back.
WRAP_ID = "stagewrap"
BUTTON_ID = "fullscreen"

#: What the button says, in each of its two states.
LABEL_ENTER = "全画面にする"
LABEL_EXIT = "全画面をやめる"

#: Tried once fullscreen is entered, ignored when it fails - which is every
#: desktop browser and some phones (§18 事実 1).
LOCK_TO = "landscape"

#: Names the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "fullSupported",
    "fullActive",
    "fullToggle",
    "fullFacts",
)

FULLSCREEN_PREAMBLE = """
/* --- 全画面ボタン (§18 事実 2, C-1416) --------------------------------- */
const FULL_WRAP=document.getElementById(FULL_WRAP_TOKEN);
const FULL_BTN=document.getElementById(FULL_BTN_TOKEN);
const FULL_ENTER=FULL_ENTER_TOKEN,FULL_EXIT=FULL_EXIT_TOKEN;
let FULL_ASKED=0,FULL_LEFT=0,FULL_LOCKS=0,FULL_REFUSED=0;
/* The prefixed spellings are iOS Safari's, which §18 事実 2 records as only
   partly there until 26.6. Reading them costs four lines and is the
   difference between a button and no button on a lot of phones. */
function fullEnabled(){
  try{return !!(document.fullscreenEnabled||document.webkitFullscreenEnabled)}
  catch(e){return false}}
function fullRequest(el){
  if(!el)return null;
  if(el.requestFullscreen)return el.requestFullscreen();
  if(el.webkitRequestFullscreen)return el.webkitRequestFullscreen();
  return null}
function fullExit(){
  if(document.exitFullscreen)return document.exitFullscreen();
  if(document.webkitExitFullscreen)return document.webkitExitFullscreen();
  return null}
function fullElement(){
  try{return document.fullscreenElement||document.webkitFullscreenElement||null}
  catch(e){return null}}
/* Supported means the browser said so *and* the page has the two elements
   to do it with. Either half missing and the button is not offered: an
   offer the page cannot keep is worse than no offer. */
function fullSupported(){return !!(FULL_WRAP&&FULL_BTN&&fullEnabled())}
function fullActive(){return fullElement()===FULL_WRAP}
/* A promise from either call may reject, and a rejection here is the
   browser declining - not a fault. Swallowed at the one place that can see
   all of them, so no call site can forget. */
function fullQuiet(p){
  try{if(p&&typeof p.then==='function'){
    p.then(function(){},function(){FULL_REFUSED++})}}
  catch(e){}
  return p}
/* Attempted only once we are actually fullscreen, and only ever attempted:
   every desktop browser refuses this, and §18 事実 1 says to ignore that
   rather than to treat it as the feature failing. */
function fullLock(){
  try{const o=(typeof screen!=='undefined')&&screen&&screen.orientation;
    if(o&&typeof o.lock==='function'){FULL_LOCKS++;fullQuiet(o.lock(FULL_LOCK_TOKEN))}}
  catch(e){}}
function fullLabel(){if(!FULL_BTN)return;
  const on=fullActive();
  FULL_BTN.textContent=on?FULL_EXIT:FULL_ENTER;
  try{FULL_BTN.setAttribute('aria-pressed',on?'true':'false')}catch(e){}}
/* The only caller of fullRequest in the whole page. */
function fullToggle(){
  if(!fullSupported())return false;
  if(fullActive()){FULL_LEFT++;fullQuiet(fullExit());return true}
  FULL_ASKED++;fullQuiet(fullRequest(FULL_WRAP));return true}
function fullSync(){if(!FULL_BTN)return;
  FULL_BTN.style.display=fullSupported()?'inline-block':'none';
  fullLabel();
  if(fullActive()){fullLock()}}
if(FULL_BTN){
  FULL_BTN.addEventListener('click',function(e){
    try{if(e&&e.preventDefault)e.preventDefault()}catch(err){}
    fullToggle();
    /* SPACE is 「撃つ」 in four of these templates. A button that keeps
       focus after it is tapped turns the fire key into a fullscreen
       toggle, so it hands focus back the moment its job is done. */
    try{if(FULL_BTN.blur)FULL_BTN.blur()}catch(err){}})}
addEventListener('fullscreenchange',fullSync);
addEventListener('webkitfullscreenchange',fullSync);
fullSync();
function fullFacts(){return {supported:fullSupported(),active:fullActive(),
  shown:!!(FULL_BTN&&FULL_BTN.style.display==='inline-block'),
  label:FULL_BTN?String(FULL_BTN.textContent||''):null,
  /* Per snapshot, not once at the end: what the button announces to a
     screen reader is a claim about a moment, and reading it after the
     second press only ever describes being back out. */
  pressed:(FULL_BTN&&FULL_BTN.getAttribute)?FULL_BTN.getAttribute('aria-pressed'):null,
  asked:FULL_ASKED,left:FULL_LEFT,locks:FULL_LOCKS,refused:FULL_REFUSED}}
"""


def preamble() -> str:
    """The script, with its element ids and labels substituted."""

    import json

    return (
        FULLSCREEN_PREAMBLE.replace("FULL_WRAP_TOKEN", json.dumps(WRAP_ID))
        .replace("FULL_BTN_TOKEN", json.dumps(BUTTON_ID))
        .replace("FULL_ENTER_TOKEN", json.dumps(LABEL_ENTER, ensure_ascii=False))
        .replace("FULL_EXIT_TOKEN", json.dumps(LABEL_EXIT, ensure_ascii=False))
        .replace("FULL_LOCK_TOKEN", json.dumps(LOCK_TO))
    )


__all__ = [
    "BUTTON_ID",
    "FULLSCREEN_PREAMBLE",
    "LABEL_ENTER",
    "LABEL_EXIT",
    "LOCK_TO",
    "PREAMBLE_NAMES",
    "WRAP_ID",
    "preamble",
]


#: Runs a generated page in node with a browser that can be told to support
#: fullscreen or not, and to grant or refuse each request. The unhandled
#: rejection handler is the point of the whole harness: rule 3 says a
#: refusal is swallowed, and the only way to know a ``.catch`` is really
#: attached is to ask the runtime whether anything escaped.
PROBE = """
const fsNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : fsNothing),
  apply: () => fsNothing, set: () => true });
const fsEscaped = [];
process.on('unhandledRejection', (why) => { fsEscaped.push(String(why)) });
globalThis.matchMedia = () => ({ matches: false, addEventListener(){}, addListener(){} });
let fsClock = 0;
globalThis.performance = { now: () => fsClock };
const fsKeys = [];
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') fsKeys.push(fn);
  if (type === 'fullscreenchange') fsChange.push(fn) };
const fsChange = [];
globalThis.Image = function(){ return fsNothing };
const fsStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in fsStore ? fsStore[k] : null),
  setItem: (k, v) => { fsStore[k] = String(v) }, removeItem: (k) => { delete fsStore[k] } };
globalThis.location = { reload: () => {} };
/* Every call the page makes, with what it made it on. "Called
   requestFullscreen" is not the claim - "asked for the wrapper, once,
   because somebody pressed the button" is. */
const fsCalls = [];
let fsCurrent = null;
function fsElement(tag, id){
  const el = { tagName: tag, id: id, style: {}, textContent: '', attrs: {},
    handlers: {}, blurred: 0, parentNode: null,
    addEventListener(name, fn){ (this.handlers[name] = this.handlers[name] || []).push(fn) },
    setAttribute(k, v){ this.attrs[k] = v }, getAttribute(k){ return this.attrs[k] },
    blur(){ this.blurred++ },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => fsNothing, width: 720, height: 320 };
  el.requestFullscreen = function(){
    fsCalls.push({ call: 'request', on: id });
    if (!GRANT_INPUT) { return Promise.reject(new Error('refused')) }
    fsCurrent = el; return Promise.resolve() };
  return el }
const fsWrap = fsElement('DIV', 'WRAP_INPUT');
const fsBtn = fsElement('BUTTON', 'BUTTON_INPUT');
const fsCanvas = fsElement('CANVAS', 'stage');
const fsById = {};
fsById[fsWrap.id] = fsWrap; fsById[fsBtn.id] = fsBtn;
globalThis.screen = { orientation: { lock: (how) => {
  fsCalls.push({ call: 'lock', on: how });
  return LOCKS_INPUT ? Promise.resolve() : Promise.reject(new Error('not here')) } } };
globalThis.document = { readyState: 'complete',
  fullscreenEnabled: SUPPORTED_INPUT,
  get fullscreenElement(){ return fsCurrent },
  exitFullscreen(){ fsCalls.push({ call: 'exit', on: fsCurrent ? fsCurrent.id : null });
    fsCurrent = null; return Promise.resolve() },
  body: { children: [] }, createElement: (tag) => fsElement(tag, ''),
  querySelector: () => null,
  getElementById: (id) => (id in fsById ? fsById[id] : fsCanvas) };
let fsQueued = null;
globalThis.requestAnimationFrame = (fn) => { fsQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function fsRun(n){ for (let i = 0; i < n && fsQueued; i++) {
  const fn = fsQueued; fsQueued = null; fsClock += 50 / 3; fn(fsClock) } }
function fsPress(){ (fsBtn.handlers.click || []).forEach(fn => fn({ preventDefault(){} })) }
function fsNotify(){ fsChange.forEach(fn => { try { fn({}) } catch (e) {} }) }
/* Left alone: loaded, played through the gate, and played some more. Rule
   1 is that none of that puts anybody in fullscreen. */
fsRun(5);
const atLoad = fullFacts();
fsKeys.forEach(fn => fn({ key: ' ', code: 'Space',
  preventDefault(){}, stopImmediatePropagation(){} }));
fsRun(30);
const untouched = fullFacts();
const callsBeforeAnyPress = fsCalls.slice();
/* ...and then somebody presses it. */
fsPress();
fsNotify();
fsRun(3);
const afterPress = fullFacts();
const blurredAfterPress = fsBtn.blurred;
/* Pressed again: the way back out. */
fsPress();
fsNotify();
fsRun(3);
const afterSecond = fullFacts();
/* The promises settle on the microtask queue, which does not run until the
   synchronous script is done - so every snapshot above was taken before
   any rejection could be handled. One turn of the loop, and the page has
   had its chance to notice: `refused` counts what it caught, `escaped`
   counts what got past it. A .catch that was written and then bypassed
   shows up as the second number rising and the first one not. */
setImmediate(function(){ setImmediate(function(){
  console.log(JSON.stringify({
    atLoad: atLoad, untouched: untouched, afterPress: afterPress,
    afterSecond: afterSecond, settled: fullFacts(),
    callsBeforeAnyPress: callsBeforeAnyPress,
    calls: fsCalls, escaped: fsEscaped, blurred: blurredAfterPress,
    label: fsBtn.textContent, display: String(fsBtn.style.display || ''),
    pressed: fsBtn.attrs['aria-pressed'] || null,
    changeWatchers: fsChange.length,
  }));
})});
"""


def probe_source(
    script: str,
    *,
    supported: bool = True,
    grant: bool = True,
    locks: bool = False,
) -> str:
    """The page's own script, wrapped so the button can be pressed in node."""

    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("SUPPORTED_INPUT", "true" if supported else "false")
        .replace("GRANT_INPUT", "true" if grant else "false")
        .replace("LOCKS_INPUT", "true" if locks else "false")
        .replace("WRAP_INPUT", WRAP_ID)
        .replace("BUTTON_INPUT", BUTTON_ID)
    )
