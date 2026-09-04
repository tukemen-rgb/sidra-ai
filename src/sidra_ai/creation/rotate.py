"""C-1415: the one line that tells a phone held upright it can be wider.

§18: the canvas keeps its 720:320 ratio at every page width, so a 390px
portrait window plays at 390x173 CSS px and the same phone turned sideways
plays at roughly twice that on each side. The page never said so.

Three rules the research and the item both set, and the shape of the code
follows from them:

1. It is a hint, not a gate. The page stays entirely playable upright; the
   line is one sentence under the canvas and nothing waits on it.
2. It is for a device that can be turned. A desktop window that happens to
   be tall is portrait too, and telling somebody to rotate their monitor is
   the product looking foolish - so a coarse pointer is part of the
   condition, the same test .touchhint already uses for the on-screen pad.
3. It belongs to the title screen. Once play starts the line is gone: a
   sentence about how to hold the phone, sitting under a running game, is
   just clutter with the player's attention on it.

Why the condition is read with ``matchMedia`` in script rather than written
as a ``@media`` block in the stylesheet, which is what §18 事実 1 describes:
rule 3 is not a media condition at all, and rule 2 and rule 3 have to agree
about one element. Two mechanisms deciding one element's visibility is how
they come to disagree. The media *queries* are the same ones - they are
evaluated in the one place that also knows whether the game has started,
and a ``change`` listener on each keeps the live rotation working, which is
the thing the CSS would have bought.
"""

from __future__ import annotations

#: The element the page carries and the script decides about.
ROTATE_ID = "rotate"

#: What it says. No number: the gain depends on the device's own aspect
#: ratio, and a page that promises 「2 倍」 on a screen where it is 1.4 has
#: told the reader something false to sound more convincing.
ROTATE_TEXT = "端末を横向きにすると、遊ぶ画面が大きくなります。"

#: The two conditions, as the queries themselves. Kept here so the tests and
#: the instrument read the same strings the page evaluates.
ROTATE_QUERIES: tuple[str, ...] = ("(orientation: portrait)", "(pointer: coarse)")

#: Names the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "rotateShown",
    "rotateHide",
    "rotateFacts",
)

ROTATE_PREAMBLE = """
/* --- 「回すと広い」を一言 (§18, C-1415) -------------------------------- */
const ROTATE_EL=document.getElementById(ROTATE_ID_TOKEN);
const ROTATE_Q=ROTATE_QUERIES_TOKEN;
let ROTATE_GONE=false;
function rotateMatch(q){
  try{const m=matchMedia(q);return !!(m&&m.matches)}catch(e){return false}}
/* Both, or nothing. A tall desktop window is portrait as well, and a hint
   telling somebody to turn their monitor sideways is the page not knowing
   what it is running on. */
function rotateWanted(){
  if(ROTATE_GONE)return false;
  for(let i=0;i<ROTATE_Q.length;i++){if(!rotateMatch(ROTATE_Q[i]))return false}
  return true}
function rotateSync(){if(!ROTATE_EL)return;
  ROTATE_EL.style.display=rotateWanted()?'block':'none'}
/* Read off the element, not off the condition: the claim is about a line a
   person can see, and a page that decided correctly and then failed to
   touch the paragraph has not shown them anything. */
function rotateShown(){
  return !!(ROTATE_EL&&ROTATE_EL.parentNode&&ROTATE_EL.style.display==='block')}
/* Play has started, so the sentence has had its moment. Taken out rather
   than hidden: it is advice about how to hold the phone, and leaving it in
   the page under a running game is clutter a screen reader still reads. */
function rotateHide(){if(ROTATE_GONE)return;ROTATE_GONE=true;
  try{if(ROTATE_EL&&ROTATE_EL.parentNode){ROTATE_EL.parentNode.removeChild(ROTATE_EL)}}
  catch(e){}
  rotateSync()}
/* Turning the phone while the title is up has to change the answer, which
   is the one thing a stylesheet would have given for free. */
for(let i=0;i<ROTATE_Q.length;i++){
  try{const m=matchMedia(ROTATE_Q[i]);
    if(m&&m.addEventListener){m.addEventListener('change',rotateSync)}
    else if(m&&m.addListener){m.addListener(rotateSync)}}catch(e){}}
rotateSync();
function rotateFacts(){return {present:!!(ROTATE_EL&&ROTATE_EL.parentNode),
  shown:rotateShown(),gone:ROTATE_GONE,
  display:ROTATE_EL?String(ROTATE_EL.style.display):null,
  wanted:rotateWanted()}}
"""


def preamble() -> str:
    """The script, with its two constants substituted."""

    import json

    return ROTATE_PREAMBLE.replace("ROTATE_ID_TOKEN", json.dumps(ROTATE_ID)).replace(
        "ROTATE_QUERIES_TOKEN", json.dumps(list(ROTATE_QUERIES))
    )


__all__ = [
    "PREAMBLE_NAMES",
    "ROTATE_ID",
    "ROTATE_PREAMBLE",
    "ROTATE_QUERIES",
    "ROTATE_TEXT",
    "preamble",
]


#: Runs a generated page in node with a screen the probe can turn. The
#: media queries are answered from variables rather than a fixed stub, so
#: the same page can be asked upright, sideways, and on a mouse - and can
#: be rotated *while it is running*, which is the case a stylesheet would
#: have handled for free and a script has to be shown to handle.
PROBE = """
const rotNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : rotNothing),
  apply: () => rotNothing, set: () => true });
let rotPortrait = PORTRAIT_INPUT, rotCoarse = COARSE_INPUT;
const rotWatchers = [];
function rotAnswer(q){
  const s = String(q);
  if (s.indexOf('portrait') >= 0) return rotPortrait;
  if (s.indexOf('landscape') >= 0) return !rotPortrait;
  if (s.indexOf('coarse') >= 0) return rotCoarse;
  if (s.indexOf('fine') >= 0) return !rotCoarse;
  /* Everything else the page asks about - reduced motion, dark mode - is
     off, which is what every other probe here assumes too. */
  return false }
globalThis.matchMedia = (q) => ({
  get matches(){ return rotAnswer(q) },
  media: String(q),
  addEventListener: (type, fn) => { rotWatchers.push(fn) },
  addListener: (fn) => { rotWatchers.push(fn) } });
/* Turning the phone: the browser re-evaluates the queries and calls the
   listeners. Both halves matter - a page that read the query once at load
   would pass every static check and do nothing when the phone moved. */
function rotTurn(portrait){ rotPortrait = portrait;
  rotWatchers.forEach(fn => { try { fn({ matches: rotPortrait }) } catch (e) {} }) }
let rotClock = 0;
globalThis.performance = { now: () => rotClock };
const rotKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') rotKeys.push(fn) };
globalThis.Image = function(){ return rotNothing };
const rotStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in rotStore ? rotStore[k] : null),
  setItem: (k, v) => { rotStore[k] = String(v) },
  removeItem: (k) => { delete rotStore[k] } };
globalThis.location = { reload: () => {} };
/* A paragraph that can actually be taken out of a page, so "gone" is a
   fact about the document rather than about a flag beside it. */
const rotBody = { children: [],
  removeChild(node){ const at = this.children.indexOf(node);
    if (at >= 0) { this.children.splice(at, 1) } node.parentNode = null; return node } };
const rotHint = { tagName: 'P', id: 'ROTATE_ID_INPUT', style: {}, parentNode: rotBody };
rotBody.children.push(rotHint);
const rotCanvas = { width: 720, height: 320, style: {},
  addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rotNothing };
globalThis.document = { readyState: 'complete', body: rotBody,
  createElement: () => rotNothing, querySelector: () => null,
  getElementById: (id) => (id === 'ROTATE_ID_INPUT' ? rotHint : rotCanvas) };
let rotQueued = null;
globalThis.requestAnimationFrame = (fn) => { rotQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function rotRun(n){ for (let i = 0; i < n && rotQueued; i++) {
  const fn = rotQueued; rotQueued = null; rotClock += 50 / 3; fn(rotClock) } }
rotRun(WARMUP_INPUT);
const atLoad = rotateFacts();
/* Turned over while the title is still up. */
rotTurn(!rotPortrait);
const afterTurn = rotateFacts();
rotTurn(!rotPortrait);
const turnedBack = rotateFacts();
let afterStart = null;
if (PRESS_INPUT) {
  rotKeys.forEach(fn => fn({ key: ' ', code: 'Space',
    preventDefault(){}, stopImmediatePropagation(){} }));
  rotRun(3);
  afterStart = rotateFacts();
  /* ...and turning it after that must not bring the line back. */
  rotTurn(true);
  afterStart.afterTurningBack = rotateFacts();
}
console.log(JSON.stringify({
  atLoad: atLoad, afterTurn: afterTurn, turnedBack: turnedBack,
  afterStart: afterStart, watchers: rotWatchers.length,
  inBody: rotBody.children.length, gate: gateFacts(),
}));
"""


def probe_source(
    script: str,
    *,
    portrait: bool = True,
    coarse: bool = True,
    press: bool = False,
    warmup: int = 3,
) -> str:
    """The page's own script, wrapped so its screen can be turned in node."""

    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PORTRAIT_INPUT", "true" if portrait else "false")
        .replace("COARSE_INPUT", "true" if coarse else "false")
        .replace("PRESS_INPUT", "true" if press else "false")
        .replace("WARMUP_INPUT", str(int(warmup)))
        .replace("ROTATE_ID_INPUT", ROTATE_ID)
    )
