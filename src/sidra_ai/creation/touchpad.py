"""An on-screen pad, so a phone can play the games a keyboard could.

Every template reads the keyboard. On a phone there is no keyboard, so
"遊べる" was a claim that only held on a desk - the harsh review's second
complaint, and one the playability number could not see: the page opens and
runs on a phone, it just cannot be played. The knowledge base
(``docs/research/game-design-notes.md`` §4) gives the shape of the fix -
touch targets of at least 48dp with 8dp between them, and controls that do
not replace the existing ones.

The mechanism is deliberately one thing, not four:

* The pad **synthesises keyboard events**. Templates keep their own
  ``keydown``/``keyup`` handlers and learn nothing about touch, so a new
  template is playable on a phone the day it is written rather than the day
  someone remembers to wire it up.
* It **draws inside the canvas**, after the game, by wrapping
  ``requestAnimationFrame`` once. A pad drawn from its own loop would be
  painted over by whichever callback ran last.
* It **appears only for a coarse pointer**. A pad on a desktop is clutter,
  and the keyboard never stops working when the pad is up.

``ALIASES`` is the one piece of knowledge shared with the measurement: WASD
is the arrow keys under a second name, and giving one action two buttons
would be worse, not more complete. Anything a template reads that is not in
``PAD_KEYS`` and not an alias of one is a control a phone cannot reach - the
state ``creation_touch_playable`` exists to catch.
"""

from __future__ import annotations

import re

from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: The keys a pad press can produce. ``key`` and ``code`` are both set on the
#: synthetic event because templates test both (``e.code==='Space'`` in one,
#: ``ev.key==='ArrowUp'`` in another).
PAD_KEYS: tuple[str, ...] = (
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    " ",
    "r",
)

#: Second names for a key the pad already sends. Read by the judge, not by
#: the page: the pad has no reason to emit both.
ALIASES: dict[str, str] = {
    "w": "ArrowUp",
    "s": "ArrowDown",
    "a": "ArrowLeft",
    "d": "ArrowRight",
    "space": " ",
}

#: CSS pixels. §4's floor is 48 with 8 between; a thumb on glass is not a
#: mouse, so the pad takes the floor as a minimum and not a target.
BUTTON_CSS_PX = 56
GAP_CSS_PX = 12

PAD_PREAMBLE = """
/* --- on-screen pad (touch only; the keyboard is untouched) ------------ */
const PADCV=document.getElementById('stage');
const PAD_BTN=%(button)d,PAD_GAP=%(gap)d;
/* R and P are flatter than the square buttons on purpose - they are the
   round's controls, not the game's - but flatter had been 0.7, which put
   them at 39.2 CSS px against §4's 48dp floor (C-1666). Nothing noticed,
   because the floor was only ever checked by a regex over the shell's CSS
   and never against a button. 0.875 keeps the flat shape and clears the
   floor with a pixel to spare (49). */
const PAD_FLAT=0.875;
let PAD_ON=matchMedia('(pointer:coarse)').matches;
const PAD_HELD=new Map();
/* The restart guard (§12 事実 4, C-1397): the pad's R sits right above
   A, so a thumb slip mid-run erased the run with no warning - NN/g's
   error-prone condition. Mid-run the button arms a hold instead of
   firing; RESTART_HOLD frames later the pair of key events flows as
   ever. End screens (roundEnded) keep the instant R - §8's instant
   retry - and the keyboard path is untouched. */
const RESTART_HOLD=30;
let PAD_RH_PID=null,PAD_RHOLD=0;
function padRunLive(){try{
  return !(typeof roundEnded==='function'&&roundEnded())}catch(e){return true}}
if(PADCV){PADCV.style.touchAction='none'}
function padScale(){const r=PADCV.getBoundingClientRect();
  return r.width?PADCV.width/r.width:1}
/* Laid out in canvas pixels from a CSS-pixel size, so the buttons stay
   thumb-sized however the page is scaled down on a small screen. Only the
   buttons this template actually reads are kept: a dead button does nothing
   and, on a phone whose play field is a few hundred pixels wide, sits over
   the game (C-1244). PAD_ACTIVE names the live keys; a template that reads
   only SPACE shows A (and R) and leaves the D-pad's space to the game. */
/* 56 and 12 are a TARGET; §4's floor is 48 and 8 (C-1720). Three rows
   want 3x56+2x12 = 192 CSS px of height, and a 720:320 canvas shown at
   §18's own portrait width - 390 CSS px - is only 173 CSS px tall. There
   was no way to spend the surplus, so instead of giving it back the pad
   put its top row ABOVE the canvas: the layout's top edge is 320-192s
   canvas px, negative for any scale over 1.667, which is every phone
   narrower than 432 CSS px. Measured: css 390 put R, P and the D-pad's up
   button at y=-34.5, outside the bitmap - not drawn, and not reachable.
   The gap is spent first (it has the most room above its floor), then the
   button, and neither goes under §4's minimum. */
const PAD_BTN_MIN=48,PAD_GAP_MIN=8;
function padMetrics(){const s=padScale();
  let b=PAD_BTN,g=PAD_GAP;
  /* The height the canvas can offer, in the same CSS pixels the floor is
     written in. */
  const budget=s>0?PADCV.height/s:PADCV.height;
  if(3*b+2*g>budget){
    g=Math.max(PAD_GAP_MIN,(budget-3*b)/2);
    if(3*b+2*g>budget){b=Math.max(PAD_BTN_MIN,(budget-2*g)/3)}}
  /* R and P stay flat only while nothing had to be given up: once the pad
     is shrinking, 0.875 of an already-reduced button falls under 48 (45.8
     at 390 CSS px), and the floor outranks the shape. */
  return {s:s,b:b*s,g:g*s,flat:(b<PAD_BTN||g<PAD_GAP)?1:PAD_FLAT}}
function padButtons(){const m=padMetrics(),s=m.s,b=m.b,g=m.g,
  W=PADCV.width,H=PADCV.height,lx=g+b,ly=H-g-b*1.5;
  return [
    {id:'ArrowLeft',x:g,y:ly-b/2,w:b,h:b,g:'left'},
    {id:'ArrowRight',x:g+2*(b+g),y:ly-b/2,w:b,h:b,g:'right'},
    {id:'ArrowUp',x:lx+g,y:ly-b/2-(b+g),w:b,h:b,g:'up'},
    {id:'ArrowDown',x:lx+g,y:ly-b/2+(b+g),w:b,h:b,g:'down'},
    {id:' ',x:W-g-b*1.4,y:ly-b/2,w:b*1.4,h:b,g:'A'},
    {id:'r',x:W-g-b*1.4,y:ly-b/2-(b+g),w:b*1.4,h:b*m.flat,g:'R'}
  ].filter(b=>PAD_ACTIVE.has(b.id)).concat(padPauseButton()||[])}
/* The gate's own control, not the game's (C-1451). Pause was reachable from
   a keyboard only: the canvas pointerdown handler leads to gateStart or
   gateGesture and nowhere else, so a phone could RESUME a paused game - a
   tap counts as "start" - but could never pause one. A one-way door, on the
   device where an interruption (a call, a ticket gate) is likeliest.
   Deliberately outside the PAD_ACTIVE filter above: that filter is about the
   keys THIS TEMPLATE reads (C-1244), and no template reads P. The page does.
   It sends the key rather than calling gateTogglePause, so pause keeps one
   definition and the pad stays the thing that turns taps into keys.
   Not on the title screen, for the reason P itself is ignored there:
   「any key」 has to mean any key. Belt and braces - while the gate is shut
   the template's frames are withheld, so the pad is not drawn either - but
   the rule is written down rather than inherited from that. */
function padPauseButton(){
  let where='playing';
  try{where=gateState()}catch(e){return null}
  if(where==='title')return null;
  const m=padMetrics(),b=m.b,g=m.g,W=PADCV.width,H=PADCV.height,
    ly=H-g-b*1.5;
  /* Beside R rather than above it (C-1666). Stacked, a button tall enough
     for a thumb (PAD_FLAT) put its top at y=67, seven pixels inside the
     band C-1417's countdown owns - and no gap that still honours the 8dp
     spacing rule would have brought it back down. The row below is empty
     to the left, so the pair sits side by side and both rules hold. */
  return {id:'p',x:W-g-b*1.4-(b*1.4+g),y:ly-b/2-(b+g),w:b*1.4,h:b*m.flat,g:'P'}}
function padAt(ev){const r=PADCV.getBoundingClientRect(),
  x=(ev.clientX-r.left)*(PADCV.width/r.width),
  y=(ev.clientY-r.top)*(PADCV.height/r.height);
  return padButtons().find(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h)||null}
const PAD_CODES={' ':'Space',r:'KeyR',p:'KeyP'};
function padKey(type,id){dispatchEvent(new KeyboardEvent(type,
  {key:id,code:PAD_CODES[id]||id,bubbles:true,cancelable:true}))}
function padDown(ev){
  if(ev.pointerType==='touch'||ev.pointerType==='pen'){PAD_ON=true}
  if(!PAD_ON)return;
  const b=padAt(ev);if(!b)return;
  /* The pad owns this tap: templates also treat a canvas tap as "act", and
     a press on the D-pad must not fire the action too. */
  ev.preventDefault();ev.stopImmediatePropagation();
  PAD_HELD.set(ev.pointerId,b.id);
  if(b.id==='r'&&padRunLive()){PAD_RH_PID=ev.pointerId;PAD_RHOLD=0;return}
  padKey('keydown',b.id)}
function padUp(ev){const id=PAD_HELD.get(ev.pointerId);if(id===undefined)return;
  ev.preventDefault();ev.stopImmediatePropagation();
  PAD_HELD.delete(ev.pointerId);
  /* A pending restart hold released early is a cancel, not a keyup:
     no keydown ever went out for it. */
  if(ev.pointerId===PAD_RH_PID){PAD_RH_PID=null;PAD_RHOLD=0;return}
  padKey('keyup',id)}
function padMove(ev){if(PAD_HELD.has(ev.pointerId)){
  ev.preventDefault();ev.stopImmediatePropagation()}}
if(PADCV){PADCV.addEventListener('pointerdown',padDown);
  PADCV.addEventListener('pointerup',padUp);
  PADCV.addEventListener('pointercancel',padUp);
  PADCV.addEventListener('pointermove',padMove)}
/* An interruption releases the pad too (§22×§4, C-1392): focusRelease
   lifts the KEYS on blur/pagehide, but this map is the pad's own state -
   left alone it keeps the held highlight lit on a button nobody is
   touching, and a browser that recycles the pointerId hands the NEXT tap
   to padMove/padUp, which eat it. The keyup here doubles focusRelease's;
   keys[k]=false twice is harmless and neither side depends on order. */
function padRelease(){PAD_RH_PID=null;PAD_RHOLD=0;
  PAD_HELD.forEach(id=>padKey('keyup',id));PAD_HELD.clear()}
addEventListener('blur',padRelease);
addEventListener('pagehide',padRelease);
function padGlyph(c,b){const cxp=b.x+b.w/2,cyp=b.y+b.h/2,r=Math.min(b.w,b.h)*0.22;
  c.fillStyle='INK_TOKEN';
  if(b.g==='A'||b.g==='R'||b.g==='P'){c.font=Math.round(r*2)+'px ui-monospace,monospace';
    c.textAlign='center';c.textBaseline='middle';c.fillText(b.g,cxp,cyp);
    c.textAlign='left';c.textBaseline='alphabetic';return}
  const d={up:[0,-1],down:[0,1],left:[-1,0],right:[1,0]}[b.g];
  c.beginPath();c.moveTo(cxp+d[0]*r,cyp+d[1]*r);
  c.lineTo(cxp-d[0]*r+d[1]*r,cyp-d[1]*r+d[0]*r);
  c.lineTo(cxp-d[0]*r-d[1]*r,cyp-d[1]*r-d[0]*r);
  c.closePath();c.fill()}
/* The pad's contrast contract (§4 WCAG 1.4.11, C-1388): the buttons sit
   on whatever the scene floor is this act, and the floor's luminance
   moves per act (§7's reserved brightness), so no single ring colour can
   hold 3:1 everywhere - border-on-raised measured 1.05:1 on paper. Two
   concentric rings at the theme's luminance extremes (surface outside,
   ink inside, both full alpha) guarantee one of the pair clears 3:1 on
   any floor. The translucent plate stays - it is backdrop, not boundary. */
function padFacts(){return {plate:'RAISED_TOKEN',alpha:0.72,
  ringOut:'SURFACE_TOKEN',ringIn:'INK_TOKEN',glyph:'INK_TOKEN'}}
function drawPad(){if(!PAD_ON||!PADCV)return;
  /* The hold ticks with the pad's own frame: reach the threshold and the
     usual key pair flows - one restart, exactly as if R were pressed. */
  if(PAD_RH_PID!==null){PAD_RHOLD++;
    if(PAD_RHOLD>=RESTART_HOLD){padKey('keydown','r');padKey('keyup','r');
      PAD_HELD.delete(PAD_RH_PID);PAD_RH_PID=null;PAD_RHOLD=0}}
  const c=PADCV.getContext('2d');c.save();
  padButtons().forEach(b=>{
    const held=[...PAD_HELD.values()].includes(b.id);
    c.globalAlpha=0.72;
    c.fillStyle=held?'CYAN_TOKEN':'RAISED_TOKEN';
    c.fillRect(b.x,b.y,b.w,b.h);
    c.globalAlpha=1;
    c.strokeStyle='SURFACE_TOKEN';c.lineWidth=4;c.strokeRect(b.x,b.y,b.w,b.h);
    c.strokeStyle='INK_TOKEN';c.lineWidth=2;c.strokeRect(b.x,b.y,b.w,b.h);
    padGlyph(c,b);
    /* The hold's receipt: a bar filling across the R button. State, not
       decoration, so it draws under reduced motion too. */
    if(b.id==='r'&&PAD_RH_PID!==null){c.fillStyle='CYAN_TOKEN';
      c.fillRect(b.x+2,b.y+b.h-5,(b.w-4)*Math.min(1,PAD_RHOLD/RESTART_HOLD),3)}});
  c.restore()}
/* Wrapped once, so the pad is drawn after whatever the game just drew. */
const PAD_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){return PAD_RAF(function(t){fn(t);drawPad()})};
""" % {"button": BUTTON_CSS_PX, "gap": GAP_CSS_PX}

#: How a template can name a key: ``e.code==='Space'``, ``ev.key==='ArrowUp'``,
#: ``keys['arrowleft']`` and the ``K('ArrowLeft')`` helper (``K(k){return
#: keys[k]}``) are all in use today, and a template is free to pick any of
#: them. The ``K('…')`` form is a call - the definition ``K(k){…}`` has no
#: quote after the paren, so it is not matched.
_READS = (
    re.compile(r"""\.code\s*===\s*['"]([A-Za-z0-9]+)['"]"""),
    re.compile(r"""\.key\s*===\s*['"]([^'"]+)['"]"""),
    re.compile(r"""\bkeys\[\s*['"]([^'"]+)['"]\s*\]"""),
    re.compile(r"""\bK\(\s*['"]([^'"]+)['"]\s*\)"""),
)

#: The shared steering helper (``parts.py``) reads its keys through
#: ``partsHeld(['ArrowLeft'])`` inside the preamble, so no literal the patterns
#: above can see appears in the template body. A template that *calls* it steers
#: with ← →; the definition ``function partsSteerX(…)`` is excluded so its
#: presence in every game (the preamble is always included) is not mistaken for
#: a call. No template passes custom key lists today, so the defaults stand.
_PARTS_STEER_CALL = re.compile(r"(?<!function )partsSteerX\(")

#: ``KeyboardEvent.code`` spellings, back to the ``key`` the pad sends.
_FROM_CODE = {"Space": " ", "KeyR": "r"}


#: A phone playing the page: taps go in at canvas coordinates, and what
#: comes back is the gate's state after each one (C-1451).
#:
#: The one fact this harness has to get right is the ORDER of the two
#: pointerdown listeners on the canvas. Both the gate and the pad register on
#: the same element, and for an event whose target IS that element the DOM
#: runs its listeners in REGISTRATION order - the capture flag decides
#: nothing here. The gate's preamble is assembled first, so the gate is
#: called first, and its ``stopImmediatePropagation`` on a shut gate is what
#: keeps a tap from reaching the pad. Modelled that way rather than
#: capture-first, which would have been the same answer for the wrong reason.
#:
#: Every name carries a ``tp`` prefix: the templates declare ``keys``,
#: ``ctx`` and ``store`` at the top level, and a harness that reuses one of
#: those stops the page from parsing at all.
TOUCH_PAUSE_PROBE = """
const tpNothing = new Proxy(function(){}, {
  get:(t,k)=>(k===Symbol.toPrimitive?()=>0:tpNothing), apply:()=>tpNothing, set:()=>true });
/* A phone: the pad only shows itself for a coarse pointer. */
globalThis.matchMedia = (q) => ({ matches: String(q).indexOf('coarse') >= 0,
  addEventListener(){}, addListener(){} });
let tpClock = 0; globalThis.performance = { now: () => tpClock };
globalThis.KeyboardEvent = function(type, init){ Object.assign(this, init || {});
  this.type = type; this.preventDefault = function(){};
  this.stopImmediatePropagation = function(){ this.tpStopped = true } };
const tpWindowKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') tpWindowKeys.push(fn) };
globalThis.dispatchEvent = (ev) => { if (ev && ev.type === 'keydown') {
  for (const fn of tpWindowKeys) { fn(ev); if (ev.tpStopped) break } } return true };
globalThis.Image = function(){ return tpNothing };
const tpStore = STORE_INPUT;
globalThis.localStorage = { getItem:k=>k in tpStore?tpStore[k]:null,
  setItem:(k,v)=>{tpStore[k]=String(v)}, removeItem:k=>{delete tpStore[k]} };
globalThis.location = { reload: () => {} };
let tpPainted = [];
const tpCtx = new Proxy({
  fillText:(t)=>{ tpPainted.push({ kind:'text', v:String(t) }) },
  fillRect:(x,y,w,h)=>{ tpPainted.push({ kind:'rect', x:Math.round(x), y:Math.round(y),
    w:Math.round(w), h:Math.round(h) }) } },
  { get:(t,k)=>(k in t?t[k]:(k===Symbol.toPrimitive?()=>0:tpNothing)), set:()=>true });
/* Listeners in one list, in registration order - see the note above. */
const tpListeners = [];
const tpCanvas = { width:720, height:320, style:{},
  addEventListener:(type, fn)=>{ tpListeners.push({ type:type, fn:fn }) },
  getBoundingClientRect:()=>({ left:0, top:0, width:720, height:320 }),
  getContext:()=>tpCtx };
globalThis.document = { readyState:'complete', body:{children:[]},
  createElement:()=>tpNothing, querySelector:()=>null, getElementById:()=>tpCanvas };
let tpQueued = null;
globalThis.requestAnimationFrame = (fn) => { tpQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function tpSend(type, ev){ ev.type = type;
  ev.preventDefault = function(){};
  ev.stopImmediatePropagation = function(){ ev.tpStopped = true };
  for (const l of tpListeners) { if (l.type !== type) continue;
    l.fn(ev); if (ev.tpStopped) break } }
function tpTap(x, y){ const ev = { clientX:x, clientY:y, pointerId:1, pointerType:'touch' };
  tpSend('pointerdown', ev);
  tpSend('pointerup', { clientX:x, clientY:y, pointerId:1, pointerType:'touch' }) }
function tpStep(n){ for (let i = 0; i < n && tpQueued; i++) {
  const fn = tpQueued; tpQueued = null; tpClock += 16; fn(tpClock) } }
function tpPause(){ try { return padButtons().find(b => b.id === 'p') || null }
  catch(e){ return null } }
const tpSeen = [];
function tpNote(what){ tpSeen.push({ what:what, gate:gateState(),
  pause:tpPause(), painted:tpPainted.slice() }); tpPainted = [] }
tpStep(3); tpNote('atLoad');
/* Into play with a tap - the only input a phone has. */
tpTap(360, 160); tpStep(4); tpNote('playing');
/* ...and now the button that did not exist: pause, by finger. */
const tpButton = tpPause();
if (tpButton) { tpTap(tpButton.x + tpButton.w / 2, tpButton.y + tpButton.h / 2) }
tpStep(3); tpNote('afterPauseTap');
/* Back out the way that already worked, so this cannot have closed a door. */
tpTap(360, 160); tpStep(4); tpNote('afterResumeTap');
console.log(JSON.stringify({ seen: tpSeen, button: tpButton,
  canvas: { w: tpCanvas.width, h: tpCanvas.height } }));
"""


def touch_pause_probe_source(script: str, *, store: dict[str, str] | None = None) -> str:
    """The page driven from a title screen to paused and back, by taps only."""

    return TOUCH_PAUSE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "STORE_INPUT", __import__("json").dumps(store or {}, ensure_ascii=False)
    )


def _normalise(name: str) -> str:
    """One spelling per physical control.

    ``code`` names fold to their ``key``, aliases fold to what they alias,
    and case is ignored throughout: a template that stores
    ``keys[e.key.toLowerCase()]`` reads ``'arrowleft'`` for the key everyone
    else spells ``'ArrowLeft'``, and treating those as two controls would
    report a phone-unreachable button that does not exist.
    """

    name = _FROM_CODE.get(name, name)
    folded = name.casefold()
    name = ALIASES.get(folded, name)
    for known in PAD_KEYS:
        if known.casefold() == name.casefold():
            return known
    return name


def keys_read(script: str) -> set[str]:
    """Every key the template's own handlers respond to, normalised."""

    found: set[str] = set()
    for pattern in _READS:
        found.update(_normalise(match) for match in pattern.findall(script))
    # A steering call reads ← → through the shared helper, invisibly to the
    # literal patterns above (C-1247): without this the pad would drop the ◀▶
    # a partsSteerX game needs on a phone.
    if _PARTS_STEER_CALL.search(script):
        found.update({"ArrowLeft", "ArrowRight"})
    return found


def pad_active_declaration(script: str) -> str:
    """The ``PAD_ACTIVE`` set for a fully assembled game script.

    ``padButtons`` draws a button only when its key is in ``PAD_ACTIVE``, so
    this names the pad keys the running page actually reads - the template body
    and every wrapper preamble folded in (restart's ``r`` and the shooter's
    space arrive from wrappers, not the template). Computed on the final
    script rather than the bare template so the pad matches what a press will
    reach, and prepended so the constant exists before any draw.
    """

    import json

    active = sorted(keys_read(script) & set(PAD_KEYS))
    return "\nconst PAD_ACTIVE=new Set(" + json.dumps(active) + ");\n"


def unreachable_keys(script: str) -> set[str]:
    """Keys this template needs that no pad button can send.

    Non-empty means the template has a control a phone cannot press - which
    is exactly the "playable" claim failing quietly, since the page still
    opens and still runs.
    """

    return keys_read(script) - set(PAD_KEYS)


#: The pad's contrast contract, read off a built page (§4 1.4.11, C-1388):
#: padFacts() reports the substituted plate/ring/glyph colours and the
#: probe walks the page's own scenePaint through all three acts so the
#: judge computes ratios against the floors the pad actually sits on.
PAD_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
globalThis.requestAnimationFrame = () => 0;
SCRIPT_PLACEHOLDER
const facts = padFacts();
const floors = [];
const keep = (typeof SCENE !== 'undefined') ? SCENE : 0;
for (let i = 0; i < 3; i++) {
  try { SCENE = i; floors.push(scenePaint(FLOOR_PLACEHOLDER)) }
  catch (e) { floors.push(null) } }
try { SCENE = keep } catch (e) {}
console.log(JSON.stringify({ facts: facts, floors: floors }));
"""


def pad_probe(script: str, *, floor_token: str) -> str:
    """The page's own script, wrapped so the pad's colours and the acts'
    real floors come back together."""

    return PAD_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "FLOOR_PLACEHOLDER", f"'{floor_token}'"
    )


#: The pad, painted rather than declared (§4, C-1390): C-1388's judge
#: computes ratios from padFacts()' declared colours, so a page that draws
#: no ring but keeps the declaration passes - the C-1337 limit, again.
#: This probe arms PAD_ON (matchMedia answers per query: coarse pointer
#: yes, reduced motion no), runs one post-gate frame through a recording
#: context that tracks fillStyle/strokeStyle/globalAlpha/lineWidth through
#: save/restore, and checks every padButtons() rect really received the
#: plate fill, both rings at their widths and full alpha, and its glyph.
PADPAINT_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = (q) => ({ matches: String(q).indexOf('coarse') >= 0 });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let S = { fill: '', stroke: '', alpha: 1, lw: 1 };
const stack = [];
let fills = [], strokes = [], texts = [], pathFills = [];
const rec = {
  fillRect: (x, y, w, h) => { fills.push([x, y, w, h, S.fill, S.alpha]) },
  strokeRect: (x, y, w, h) => { strokes.push([x, y, w, h, S.stroke, S.lw, S.alpha]) },
  fillText: (txt) => { texts.push([String(txt), S.fill, S.alpha]) },
  fill: () => { pathFills.push([S.fill, S.alpha]) },
  save: () => { stack.push({ fill: S.fill, stroke: S.stroke, alpha: S.alpha, lw: S.lw }) },
  restore: () => { const p = stack.pop(); if (p) S = p },
};
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy(rec, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: (t, k, v) => { if (k === 'fillStyle') S.fill = v;
      else if (k === 'strokeStyle') S.stroke = v;
      else if (k === 'globalAlpha') S.alpha = v;
      else if (k === 'lineWidth') S.lw = v; return true } }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(3);
const facts = padFacts();
const buttons = padButtons();
fills = []; strokes = []; texts = []; pathFills = [];
run(1);
const report = buttons.map(b => {
  const isLetter = b.g.length === 1;
  return { id: b.id, g: b.g,
    plate: fills.some(f => f[0] === b.x && f[1] === b.y && f[2] === b.w &&
      f[3] === b.h && f[4] === facts.plate && f[5] === facts.alpha),
    ringOut: strokes.some(f => f[0] === b.x && f[1] === b.y && f[2] === b.w &&
      f[3] === b.h && f[4] === facts.ringOut && f[5] === 4 && f[6] === 1),
    ringIn: strokes.some(f => f[0] === b.x && f[1] === b.y && f[2] === b.w &&
      f[3] === b.h && f[4] === facts.ringIn && f[5] === 2 && f[6] === 1),
    glyph: isLetter
      ? texts.some(t => t[0] === b.g && t[1] === facts.glyph && t[2] === 1)
      : null } });
const arrows = buttons.filter(b => b.g.length > 1).length;
const arrowGlyphs = pathFills.filter(p => p[0] === facts.glyph && p[1] === 1).length;
console.log(JSON.stringify({ padOn: PAD_ON, buttons: report,
  arrows: arrows, arrowGlyphs: arrowGlyphs }));
"""



#: How big the pad's buttons actually come out, in the units a thumb cares
#: about (§4, C-1666). The 48dp rule was pinned on the shell's CSS by a
#: regex over the generated HTML - `evals/touch_targets.py` never starts
#: node, and its own docstring says the end-to-end proof "ran at fix" -
#: while the canvas pad, the only way to play this on a phone, had its
#: paint and its contrast checked but never its size.
#:
#: Measured off the drawn rectangles and divided by the page's own
#: padScale(), because the layout is canvas pixels and the rule is CSS
#: pixels: on a narrow screen the same button is fewer canvas pixels, and
#: that is precisely the direction where a thumb-sized control stops
#: being one.
PADSIZE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = (q) => ({ matches: String(q).indexOf('coarse') >= 0 });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let fills = [];
const rec = { fillRect: (x, y, w, h) => { fills.push([x, y, w, h]) } };
/* The canvas is CANVAS_W wide in its own pixels but CSS_W wide on the
   glass: that ratio IS padScale(), and it is what turns a layout into a
   thumb. */
globalThis.document = { getElementById: () => ({
  width: CANVAS_W, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width: CSS_W, height: 320}),
  getContext: () => new Proxy(rec, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
PROBE_SEND_PLACEHOLDER
probeSend('keydown', ' ', handlers); probeSend('keyup', ' ', handlers);
run(3);
const scale = padScale();
const buttons = padButtons();
fills = [];
run(1);
/* Only the rectangles the page drew for the buttons themselves. */
const plates = buttons.map(b => {
  const hit = fills.filter(f => Math.abs(f[0] - b.x) < 0.5 && Math.abs(f[1] - b.y) < 0.5 &&
    Math.abs(f[2] - b.w) < 0.5 && Math.abs(f[3] - b.h) < 0.5);
  return { id: b.id, drawn: hit.length > 0,
    css: Math.min(b.w, b.h) / scale,
    /* On the glass at all: a button laid out above the top edge is not a
       small target, it is an absent one (C-1720 - at §18's own portrait
       width the top row sat at y=-34, outside the bitmap). A hundredth of
       a canvas pixel of tolerance, because the layout fills the height
       exactly when it has to and `H - x` then `+ x` finishes one ulp out;
       that is arithmetic dust, not a button off the screen. */
    onCanvas: b.x >= -0.01 && b.y >= -0.01 &&
      b.x + b.w <= PADCV.width + 0.01 && b.y + b.h <= PADCV.height + 0.01,
    x: b.x / scale, y: b.y / scale, w: b.w / scale, h: b.h / scale } });
/* The smallest gap between any two buttons, and whether any two overlap.
   A spacing rule that does not also forbid overlap is not a spacing rule. */
let minGap = Infinity, overlaps = 0;
for (let i = 0; i < plates.length; i++) {
  for (let j = i + 1; j < plates.length; j++) {
    const a = plates[i], b = plates[j];
    const dx = Math.max(a.x - (b.x + b.w), b.x - (a.x + a.w));
    const dy = Math.max(a.y - (b.y + b.h), b.y - (a.y + a.h));
    if (dx < 0 && dy < 0) { overlaps++; continue }
    minGap = Math.min(minGap, Math.max(dx, dy));
  }
}
console.log(JSON.stringify({ padOn: PAD_ON, scale: scale,
  canvasW: CANVAS_W, cssW: CSS_W, count: plates.length,
  allDrawn: plates.every(p => p.drawn),
  allOnCanvas: plates.every(p => p.onCanvas),
  smallest: plates.length ? Math.min.apply(null, plates.map(p => p.css)) : 0,
  minGap: minGap === Infinity ? null : minGap, overlaps: overlaps,
  plates: plates }));
"""


def padsize_probe(script: str, *, canvas_w: int = 720, css_w: int = 720) -> str:
    """The page's own script, wrapped so a thumb's worth can be measured."""

    from sidra_ai.creation.probekit import PROBE_SEND

    return (
        PADSIZE_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_SEND_PLACEHOLDER", PROBE_SEND)
        .replace("CANVAS_W", str(int(canvas_w)))
        .replace("CSS_W", str(int(css_w)))
    )


def padpaint_probe(script: str) -> str:
    """The page's own script, wrapped so the pad's real paint is compared
    against its own declaration."""

    return PADPAINT_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The interrupted touch, released (§22×§4, C-1392): one real synthetic
#: touch on a pad button, then a blur with no pointerup - the map must
#: empty, the keyup must flow, and the next frame's plates must all be
#: back to the declared plate colour instead of one stuck held highlight.
PADHOLD_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {}, cvHandlers = {}, sent = [];
globalThis.matchMedia = (q) => ({ matches: String(q).indexOf('coarse') >= 0 });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.KeyboardEvent = function(type, init){ this.type = type;
  Object.assign(this, init);
  this.preventDefault = () => {}; this.stopImmediatePropagation = () => {} };
globalThis.dispatchEvent = (e) => { sent.push([e.type, e.key]);
  (handlers[e.type] || []).forEach(fn => fn(e)); return true };
globalThis.Image = function(){ return nothing };
let S = { fill: '', alpha: 1 };
const stack = [];
let fills = [];
const rec = {
  fillRect: (x, y, w, h) => { fills.push([x, y, w, h, S.fill]) },
  save: () => { stack.push({ fill: S.fill, alpha: S.alpha }) },
  restore: () => { const p = stack.pop(); if (p) S = p },
};
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: (type, fn) => {
    (cvHandlers[type] = cvHandlers[type] || []).push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy(rec, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: (t, k, v) => { if (k === 'fillStyle') S.fill = v;
      else if (k === 'globalAlpha') S.alpha = v; return true } }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(3);
const facts = padFacts();
const b0 = padButtons()[0];
function plateAt(b){ const hit = fills.filter(f => f[0] === b.x && f[1] === b.y &&
  f[2] === b.w && f[3] === b.h);
  return hit.length ? hit[hit.length - 1][4] : null }
/* One real touch on the first button, through the pad's own listener. */
(cvHandlers.pointerdown || []).forEach(fn => fn({ pointerType: 'touch',
  pointerId: 7, clientX: b0.x + b0.w / 2, clientY: b0.y + b0.h / 2,
  preventDefault(){}, stopImmediatePropagation(){} }));
const heldBefore = PAD_HELD.size;
const downSent = sent.filter(s => s[0] === 'keydown' && s[1] === b0.id).length;
fills = []; run(1);
const heldPlateBefore = plateAt(b0);
/* The interruption: blur, and no pointerup ever. */
sent.length = 0;
(handlers.blur || []).forEach(fn => fn({}));
const heldAfter = PAD_HELD.size;
const upSent = sent.filter(s => s[0] === 'keyup' && s[1] === b0.id).length;
fills = []; run(1);
const heldPlateAfter = plateAt(b0);
console.log(JSON.stringify({ heldBefore: heldBefore, downSent: downSent,
  heldPlateBefore: heldPlateBefore === facts.plate ? 'plate' : 'held',
  heldAfter: heldAfter, upSent: upSent,
  heldPlateAfter: heldPlateAfter === facts.plate ? 'plate' : 'held' }));
"""


def padhold_probe(script: str) -> str:
    """The page's own script, wrapped so the interrupted touch's release
    can be watched."""

    return PADHOLD_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The restart guard, driven (§12 事実 4, C-1397): a mid-run tap on the
#: pad's R must send nothing and change nothing; a full hold must send
#: exactly one keydown/keyup pair and really reset; the bar must be on
#: screen mid-hold; and on the end screen the same tap fires instantly.
PADR_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {}, cvHandlers = {}, sent = [];
globalThis.matchMedia = (q) => ({ matches: String(q).indexOf('coarse') >= 0 });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.KeyboardEvent = function(type, init){ this.type = type;
  Object.assign(this, init);
  this.preventDefault = () => {}; this.stopImmediatePropagation = () => {} };
globalThis.dispatchEvent = (e) => { sent.push([e.type, e.key]);
  (handlers[e.type] || []).forEach(fn => fn(e)); return true };
globalThis.Image = function(){ return nothing };
let fills = [];
const rec = {
  fillRect: (x, y, w, h) => { fills.push([x, y, w, h]) },
  save(){}, restore(){},
};
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: (type, fn) => {
    (cvHandlers[type] = cvHandlers[type] || []).push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy(rec, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  let stopped = false;
  /* The pairing comes from probekeys; the stop stays here, because
     `if (stopped) break` below reads it (C-1654 第 5 陣). */
  const e = probeKey(k);
  e.stopImmediatePropagation = () => { stopped = true };
  for (const fn of (handlers[type] || [])) { fn(e); if (stopped) break }
}
function touch(type, pid, x, y){
  (cvHandlers[type] || []).forEach(fn => fn({ pointerType: 'touch',
    pointerId: pid, clientX: x, clientY: y,
    preventDefault(){}, stopImmediatePropagation(){} }));
}
function rSent(){ return sent.filter(s => s[1] === 'r') }
ev('keydown', ' '); ev('keyup', ' ');
run(3);
const rb = padButtons().filter(b => b.id === 'r')[0];
const cxr = rb.x + rb.w / 2, cyr = rb.y + rb.h / 2;
/* A mid-run tap: nothing may flow, nothing may reset. */
score = 777;
touch('pointerdown', 7, cxr, cyr);
touch('pointerup', 7, cxr, cyr);
run(2);
const tap = { sent: rSent().length, score: score };
/* A full hold: the bar on screen halfway, one key pair at the end. */
touch('pointerdown', 8, cxr, cyr);
run(15);
fills = []; run(1);
const bar = fills.some(f => f[0] === rb.x + 2 && f[1] === rb.y + rb.h - 5 &&
  f[2] > 0 && f[2] < rb.w - 4 && f[3] === 3);
run(20);
touch('pointerup', 8, cxr, cyr);
const held = { down: rSent().filter(s => s[0] === 'keydown').length,
  up: rSent().filter(s => s[0] === 'keyup').length, score: score };
/* The end screen keeps the instant R (§8). */
state = 'over';
sent.length = 0;
touch('pointerdown', 9, cxr, cyr);
const endDown = rSent().filter(s => s[0] === 'keydown').length;
touch('pointerup', 9, cxr, cyr);
run(1);
console.log(JSON.stringify({ tap: tap, bar: bar, held: held,
  endDown: endDown, stateAfter: state }));
"""


def padr_probe(script: str) -> str:
    """The page's own script, wrapped so the restart guard's three moods
    - tap, hold, end screen - can be watched."""

    return PADR_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "ALIASES",
    "BUTTON_CSS_PX",
    "GAP_CSS_PX",
    "PAD_KEYS",
    "PAD_PREAMBLE",
    "PAD_PROBE",
    "PADPAINT_PROBE",
    "PADHOLD_PROBE",
    "PADR_PROBE",
    "keys_read",
    "pad_active_declaration",
    "pad_probe",
    "padpaint_probe",
    "padhold_probe",
    "padr_probe",
    "unreachable_keys",
]
