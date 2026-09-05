"""The HUD, as painted - not as declared (§4, C-1352).

C-1337's destruction experiments recorded the limit this closes: the
contrast judge blends ``hudFacts()``'s DECLARED ink, plate and alpha over
measured skies, so a template that deletes the painting while keeping the
constants scores full marks with an invisible HUD. The same shape came up
twice more (C-1348, C-1351: a facts function does not prove a drawing).

This probe runs a generated page on a recording 2D context - assignments
to ``fillStyle`` and ``globalAlpha`` are tracked, every ``fillRect`` and
``fillText`` is written down with the style and alpha it was made under -
presses start, lets the game paint, and reports the last frame's actual
draw calls next to the page's own ``hudFacts()``. The judge then checks
that the declared plate colour was really filled at the declared alpha
and the declared ink really wrote text. A declaration nothing paints
cannot pass; a painting that drifted from its declaration cannot either.
"""

from __future__ import annotations

PAINT_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
/* The recording context: what was really painted, in what style, at what
   alpha. Only fills and text are the HUD's medium; everything else is
   swallowed so any template's draw() runs whole. */
let paintOps = [];
const paintCtx = new Proxy({
  fillRect: function(x, y, w, h){ paintOps.push({ t: 'r', s: String(this.fillStyle),
    a: Number(this.globalAlpha), x: Number(x), y: Number(y),
    w: Number(w), h: Number(h) }) },
  fillText: function(txt, x, y){ paintOps.push({ t: 't', s: String(this.fillStyle),
    a: Number(this.globalAlpha), x: Number(x), y: Number(y) }) },
  fillStyle: '', globalAlpha: 1,
}, {
  get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
  set: (t, k, v) => { if (k === 'fillStyle' || k === 'globalAlpha') { t[k] = v } return true },
});
globalThis.document = { readyState: 'complete',
  createElement: () => nothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {},
    addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => paintCtx }) };
let queued = [];
globalThis.requestAnimationFrame = (fn) => { queued.push(fn); return queued.length };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued.length; i++) {
  const due = queued; queued = []; paintOps = [];
  for (const fn of due) { fn((F++) * 16) } } }
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' ');
run(90);
console.log(JSON.stringify({ hud: hudFacts(), ops: paintOps }));
"""


def paint_probe(script: str) -> str:
    """The page's own script, wrapped so its real paint can be read."""

    return PAINT_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = ["PAINT_PROBE", "paint_probe"]
