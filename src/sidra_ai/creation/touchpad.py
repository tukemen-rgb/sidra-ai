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
let PAD_ON=matchMedia('(pointer:coarse)').matches;
const PAD_HELD=new Map();
if(PADCV){PADCV.style.touchAction='none'}
function padScale(){const r=PADCV.getBoundingClientRect();
  return r.width?PADCV.width/r.width:1}
/* Laid out in canvas pixels from a CSS-pixel size, so the buttons stay
   thumb-sized however the page is scaled down on a small screen. Only the
   buttons this template actually reads are kept: a dead button does nothing
   and, on a phone whose play field is a few hundred pixels wide, sits over
   the game (C-1244). PAD_ACTIVE names the live keys; a template that reads
   only SPACE shows A (and R) and leaves the D-pad's space to the game. */
function padButtons(){const s=padScale(),b=PAD_BTN*s,g=PAD_GAP*s,
  W=PADCV.width,H=PADCV.height,lx=g+b,ly=H-g-b*1.5;
  return [
    {id:'ArrowLeft',x:g,y:ly-b/2,w:b,h:b,g:'left'},
    {id:'ArrowRight',x:g+2*(b+g),y:ly-b/2,w:b,h:b,g:'right'},
    {id:'ArrowUp',x:lx+g,y:ly-b/2-(b+g),w:b,h:b,g:'up'},
    {id:'ArrowDown',x:lx+g,y:ly-b/2+(b+g),w:b,h:b,g:'down'},
    {id:' ',x:W-g-b*1.4,y:ly-b/2,w:b*1.4,h:b,g:'A'},
    {id:'r',x:W-g-b*1.4,y:ly-b/2-(b+g),w:b*1.4,h:b*0.7,g:'R'}
  ].filter(b=>PAD_ACTIVE.has(b.id))}
function padAt(ev){const r=PADCV.getBoundingClientRect(),
  x=(ev.clientX-r.left)*(PADCV.width/r.width),
  y=(ev.clientY-r.top)*(PADCV.height/r.height);
  return padButtons().find(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h)||null}
function padKey(type,id){dispatchEvent(new KeyboardEvent(type,
  {key:id,code:id===' '?'Space':(id==='r'?'KeyR':id),bubbles:true,cancelable:true}))}
function padDown(ev){
  if(ev.pointerType==='touch'||ev.pointerType==='pen'){PAD_ON=true}
  if(!PAD_ON)return;
  const b=padAt(ev);if(!b)return;
  /* The pad owns this tap: templates also treat a canvas tap as "act", and
     a press on the D-pad must not fire the action too. */
  ev.preventDefault();ev.stopImmediatePropagation();
  PAD_HELD.set(ev.pointerId,b.id);padKey('keydown',b.id)}
function padUp(ev){const id=PAD_HELD.get(ev.pointerId);if(id===undefined)return;
  ev.preventDefault();ev.stopImmediatePropagation();
  PAD_HELD.delete(ev.pointerId);padKey('keyup',id)}
function padMove(ev){if(PAD_HELD.has(ev.pointerId)){
  ev.preventDefault();ev.stopImmediatePropagation()}}
if(PADCV){PADCV.addEventListener('pointerdown',padDown);
  PADCV.addEventListener('pointerup',padUp);
  PADCV.addEventListener('pointercancel',padUp);
  PADCV.addEventListener('pointermove',padMove)}
function padGlyph(c,b){const cxp=b.x+b.w/2,cyp=b.y+b.h/2,r=Math.min(b.w,b.h)*0.22;
  c.fillStyle='BORDER_TOKEN';
  if(b.g==='A'||b.g==='R'){c.font=Math.round(r*2)+'px ui-monospace,monospace';
    c.textAlign='center';c.textBaseline='middle';c.fillText(b.g,cxp,cyp);
    c.textAlign='left';c.textBaseline='alphabetic';return}
  const d={up:[0,-1],down:[0,1],left:[-1,0],right:[1,0]}[b.g];
  c.beginPath();c.moveTo(cxp+d[0]*r,cyp+d[1]*r);
  c.lineTo(cxp-d[0]*r+d[1]*r,cyp-d[1]*r+d[0]*r);
  c.lineTo(cxp-d[0]*r-d[1]*r,cyp-d[1]*r-d[0]*r);
  c.closePath();c.fill()}
function drawPad(){if(!PAD_ON||!PADCV)return;
  const c=PADCV.getContext('2d');c.save();c.globalAlpha=0.72;
  padButtons().forEach(b=>{
    const held=[...PAD_HELD.values()].includes(b.id);
    c.fillStyle=held?'CYAN_TOKEN':'RAISED_TOKEN';
    c.fillRect(b.x,b.y,b.w,b.h);
    c.strokeStyle='BORDER_TOKEN';c.lineWidth=2;c.strokeRect(b.x,b.y,b.w,b.h);
    padGlyph(c,b)});
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


__all__ = [
    "ALIASES",
    "BUTTON_CSS_PX",
    "GAP_CSS_PX",
    "PAD_KEYS",
    "PAD_PREAMBLE",
    "keys_read",
    "pad_active_declaration",
    "unreachable_keys",
]
