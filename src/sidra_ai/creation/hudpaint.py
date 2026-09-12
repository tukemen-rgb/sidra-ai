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

from sidra_ai.creation.probekeys import KEY_EVENT_JS

PAINT_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
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


#: How big a drawn word really is (§24, C-1725). §24 says the type floor
#: has to be decided in EFFECTIVE size - a canvas pixel shrinks with the
#: page - and the judge that held it read `font='13px` out of the HTML with
#: a regex, which is the canvas number and not the effective one. This
#: stages a real screen width, records the font in force at every
#: fillText, and reports what the eye would get.
TEXTSIZE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
const CSS_W = CSS_W_PLACEHOLDER;
let words = [], plates = [];
const textCtx = new Proxy({
  font: '', textAlign: '', textBaseline: '', globalAlpha: 1,
  fillText: function(txt, x, y){ words.push({ font: String(this.font), text: String(txt),
    x: Number(x), y: Number(y), base: String(this.textBaseline || 'alphabetic') }) },
  /* The HUD plate is the only rect drawn at a partial alpha (HUD_A), so
     the backdrop a word sits on can be told from the world behind it. */
  fillRect: function(x, y, w, h){ if (this.globalAlpha > 0 && this.globalAlpha < 1) {
    plates.push({ x: Number(x), y: Number(y), w: Number(w), h: Number(h) }) } },
}, {
  get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
  set: (t, k, v) => { if (k === 'font' || k === 'textAlign' || k === 'textBaseline'
    || k === 'globalAlpha') { t[k] = v } return true },
});
const stage = { width: 720, height: 320, style: {},
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width: CSS_W, height: 320 * CSS_W / 720}),
  getContext: () => textCtx };
globalThis.document = { readyState: 'complete',
  createElement: () => nothing, querySelector: () => null,
  getElementById: () => stage, addEventListener: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
PROBE_KEYS_PLACEHOLDER
SCRIPT_PLACEHOLDER
let F = 0;
function turn(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(k){ const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e)) }
/* The title screen first - its two lines of controls ride the shared
   preamble onto all ten - then play, so the HUD and any toast are drawn
   too, then long enough for the round to end and its strip to appear. */
turn(3);
const title = words.slice(); words = []; plates = [];
key(' ');
let frameWords = [], framePlates = [];
for (let i = 0; i < 4200; i++) {
  if (i % 7 === 0) { key(' ') }
  /* One frame on its own, mid-play, so a word and the plate under it come
     from the same picture rather than from a thousand frames piled up -
     and from the picture the HUD is actually drawn in, not the ending. */
  if (i === 200) { words = []; plates = [] }
  turn(1);
  if (i === 200) { frameWords = words.slice(); framePlates = plates.slice() }
}
const played = words.slice();
function sizes(list){
  const out = {};
  list.forEach(function(w){
    const m = /^([0-9.]+)px/.exec(w.font);
    if (!m) { out['?'] = (out['?'] || 0) + 1; return }
    const px = Number(m[1]);
    const key = px.toFixed(2);
    if (!out[key]) { out[key] = { px: px, effective: px * CSS_W / 720, n: 0, longest: 0,
      top: Infinity, bottom: -Infinity } }
    out[key].n++;
    out[key].longest = Math.max(out[key].longest, w.text.length);
    /* The box a word occupies. 'middle' centres it; everything else here
       draws on the alphabetic baseline, where a monospace cap reaches
       about 0.8em up and a descender about 0.2em down. */
    const up = w.base === 'middle' ? px * 0.5 : px * 0.8;
    const down = w.base === 'middle' ? px * 0.5 : px * 0.2;
    if (isFinite(w.y)) {
      out[key].top = Math.min(out[key].top, w.y - up);
      out[key].bottom = Math.max(out[key].bottom, w.y + down);
    }
  });
  return out;
}
/* The one frame, word by word: the judge needs a box and a backdrop, not
   a histogram. Kept small by dropping exact repeats. */
function spans(list){
  const seen = {}, out = [];
  list.forEach(function(w){
    const m = /^([0-9.]+)px/.exec(w.font); if (!m) { return }
    const px = Number(m[1]);
    const wide = w.text.length * px;
    const left = w.align === 'center' ? w.x - wide / 2
      : (w.align === 'right' ? w.x - wide : w.x);
    const up = w.base === 'middle' ? px * 0.5 : px * 0.8;
    const down = w.base === 'middle' ? px * 0.5 : px * 0.2;
    const box = { px: px, x0: left, x1: left + wide,
      y0: w.y - up, y1: w.y + down, text: w.text.slice(0, 12) };
    const key = [px, box.x0.toFixed(1), box.y0.toFixed(1), w.text.length].join('|');
    if (seen[key]) { return }
    seen[key] = 1; out.push(box);
  });
  return out;
}
console.log(JSON.stringify({ cssW: CSS_W, scale: 720 / CSS_W,
  title: sizes(title), played: sizes(played),
  frame: spans(frameWords), plates: framePlates,
  titleWords: title.length, playedWords: played.length }));
"""


def textsize_probe(script: str, *, css_w: int = 720) -> str:
    """The page's own script, wrapped so a word's real size can be read."""

    from sidra_ai.creation import probekeys

    return probekeys.with_probe_keys(
        TEXTSIZE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
            "CSS_W_PLACEHOLDER", str(int(css_w))
        )
    )


__all__ = ["PAINT_PROBE", "paint_probe", "TEXTSIZE_PROBE", "textsize_probe"]
