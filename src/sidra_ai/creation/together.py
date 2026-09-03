"""All ten of them at once, in the same page, on the same frame.

C-1104 to C-1116 went in over twelve hours. Every one of them has its own
judge and every one of those judges says 1 - but each drives the page with
its own feature turned on and the others left at their defaults. Nobody had
run the round clock, the failure beat, the result strip, the daily seed,
the cosmetic unlock, the share line, the tuning panel and the instant start
*together*, which is the only way a person will ever run them.

Interactions are not bugs in any one feature, so no single feature's judge
can see them. The three kinds worth looking for here:

* **Storage.** Five features now write to ``localStorage``. Two that chose
  the same key would silently destroy each other's state, and the symptom
  would be a best score that resets or a skin that un-earns itself.
* **The result strip.** The clock's banner, the score line, the
  personal-best gap, the daily stamp, the "copy" hint and the unlock notice
  all land in the same thirty pixels at the bottom of the canvas. Each was
  added while the others were off.
* **Ordering.** The gate that opens itself (C-1111) removes the press that
  used to start the round clock and unlock the audio. Whether the clock
  still measures played time, and whether the failure beat still has a
  sound to play, are questions about the pair rather than about either.

Where a finding is worth fixing it gets fixed; where nothing is found the
number says so and the run that produced it is written down. "We looked and
there was nothing" is a result, but only if the looking was real.
"""

from __future__ import annotations

import json
import re

#: Every ``localStorage`` key the generated page is allowed to touch, as a
#: prefix that must be followed by the template's own name. Declared here so
#: a sixth feature that picks an existing prefix fails the sweep instead of
#: quietly overwriting whichever feature got there first.
STORAGE_PREFIXES: dict[str, str] = {
    "sidra.tune.": "C-1113 the tuning panel's values",
    "sidra.best.": "C-1106 the personal best",
    "sidra.total.": "C-1109 the cumulative score",
    "sidra.skin.": "C-1109 the colour being worn",
    "sidra.seen.": "C-1111 whether the briefing has been read",
}

#: The canvas the templates are drawn on, and the font the strip uses. Used
#: to work out whether a line that now carries six things still fits.
CANVAS_WIDTH = 720
STRIP_FONT_PX = 13

_KEY = re.compile(r"'(sidra\.[a-z]+\.)'")


def storage_keys(script: str) -> list[str]:
    """Every ``sidra.*`` key prefix the assembled page mentions."""

    return sorted(set(_KEY.findall(script)))


def key_gaps(script: str) -> list[str]:
    """Where the page's storage and the declared contract disagree."""

    seen = set(storage_keys(script))
    declared = set(STORAGE_PREFIXES)
    gaps = [f"undeclared storage key {key!r}" for key in sorted(seen - declared)]
    gaps += [f"declared but unused: {key!r}" for key in sorted(declared - seen)]
    return gaps


def text_width(line: str, *, px: int = STRIP_FONT_PX) -> float:
    """Roughly how wide a line is in the strip's monospace font.

    Half-width characters advance about 0.6em in the ui-monospace stack;
    the CJK the strip is mostly made of is full-width and advances a whole
    one. Rough is enough - the question is whether a line that grew by two
    more clauses still fits on a 720px canvas, not what it measures to the
    pixel.
    """

    total = 0.0
    for ch in line:
        code = ord(ch)
        wide = (
            0x1100 <= code <= 0x115F
            or 0x2E80 <= code <= 0xA4CF
            or 0xAC00 <= code <= 0xD7A3
            or 0xF900 <= code <= 0xFAFF
            or 0xFE30 <= code <= 0xFE6F
            or 0xFF00 <= code <= 0xFF60
            or 0xFFE0 <= code <= 0xFFE6
            or code > 0x1F000
        )
        total += px if wide else px * 0.6
    return total


#: Everything on at once: the briefing already read, a colour earned and
#: worn, today's board, a speed the player chose by hand, and a personal
#: best to be short of. Then a whole round, and then the copy button.
PROBE = """
const allNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : allNothing),
  apply: () => allNothing, set: () => true });
let allRnd = 2463534242;
Math.random = () => { allRnd ^= allRnd << 13; allRnd ^= allRnd >>> 17;
  allRnd ^= allRnd << 5; return ((allRnd >>> 0) % 100000) / 100000 };
class AllDate {
  constructor(){ return AllDate.parse() }
  static parse(){ const [y, m, d] = 'STAMP_INPUT'.split('-').map(Number);
    return { getFullYear: () => y, getMonth: () => m - 1, getDate: () => d } }
}
globalThis.Date = AllDate;
globalThis.matchMedia = () => ({ matches: false });
let allClock = 0;
globalThis.performance = { now: () => allClock };
const allKeys = [], allUps = [], allPointers = [];
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') allKeys.push(fn);
  if (type === 'keyup') allUps.push(fn) };
globalThis.Image = function(){ return allNothing };
const allStored = STORED_INPUT;
const allWrites = [];
globalThis.localStorage = {
  getItem: (k) => (k in allStored ? allStored[k] : null),
  setItem: (k, v) => { allWrites.push(k); allStored[k] = String(v) },
  removeItem: (k) => { delete allStored[k] } };
Object.defineProperty(globalThis, 'navigator', { configurable: true, writable: true,
  value: { clipboard: { writeText: (t) => { allClipboard.push(String(t)) } } } });
const allClipboard = [];
/* Everything drawn at the bottom of the canvas, with its y, so two
   features writing into the same band are visible as such. */
const allText = [], allColours = new Set();
const allCtx = new Proxy({
  fillText: (t, x, y) => { allText.push({ text: String(t), y: Math.round(Number(y)) }) },
  set fillStyle(v){ if (typeof v === 'string') allColours.add(v.toLowerCase()) },
  get fillStyle(){ return '' },
}, { get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : allNothing)),
     set: (t, k, v) => { if (k in t) { t[k] = v } return true } });
const allCanvas = { width: 720, height: 320, style: {},
  addEventListener: (type, fn) => { if (type === 'pointerdown') allPointers.push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => allCtx };
function allElement(tag){
  const el = { tagName: tag, style: {}, children: [], attrs: {}, handlers: {}, value: '',
    appendChild(c){ this.children.push(c); return c }, remove(){}, select(){},
    setAttribute(k, v){ this.attrs[k] = v }, getAttribute(k){ return this.attrs[k] },
    addEventListener(name, fn){ (this.handlers[name] = this.handlers[name] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => allCtx, width: 720, height: 320 };
  return el }
const allBody = allElement('body');
globalThis.document = { readyState: 'complete', body: allBody,
  createElement: allElement, querySelector: () => null, execCommand: () => true,
  getElementById: () => allCanvas };
globalThis.location = { reload: () => {} };
let allQueued = null;
globalThis.requestAnimationFrame = (fn) => { allQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function allRun(n){ for (let i = 0; i < n && allQueued; i++) {
  const fn = allQueued; allQueued = null; allClock += 50 / 3; fn(allClock) } }
/* Untouched. With the briefing already read this must already be playing,
   and it must not have made a sound. */
allRun(2);
const atLoad = { gate: gateFacts(), round: roundFacts(),
  speed: SPEED_PROBE, accent: TUNE_ACCENT, skin: skinFacts() };
function allPress(key, code){
  const ev = { key: key, code: code, clientX: 360, clientY: 160,
    pointerType: 'touch', pointerId: 1,
    preventDefault(){}, stopImmediatePropagation(){} };
  allKeys.forEach(fn => fn(ev)); return ev }
function allRelease(ev){ allUps.forEach(fn => fn(ev)) }
function allTap(){ allPointers.forEach(fn => fn({ pointerType: 'touch', pointerId: 1,
  clientX: 340, clientY: 150, preventDefault(){}, stopImmediatePropagation(){} })) }
const ALL_DIRS = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'];
let allHeld = null, allEnded = false, allFrames = 0;
for (let f = 0; f < FRAMES_INPUT && allQueued && !allEnded; f++) {
  if (f % 30 === 0) {
    if (allHeld) { allRelease(allHeld) }
    const dir = ALL_DIRS[(f / 30) % ALL_DIRS.length];
    allHeld = allPress(dir, dir) }
  if (f % 15 === 0) { allRelease(allPress(' ', 'Space')); allTap() }
  const fn = allQueued; allQueued = null;
  allClock += 50 / 3;
  fn(allClock);
  allFrames = f + 1;
  const now = roundFacts();
  if (f > 60 && (now.done || now.ended)) { allEnded = true }
}
const atBreak = { round: roundFacts(), beats: failBeats(), skin: skinFacts() };
allText.length = 0;
/* Untouched frames, and more than a couple of them: the failure beat that
   fires at the timeout calls hitstop, and hitstop holds the frame - so the
   first frames of the result screen deliberately draw nothing at all. Two
   frames saw an empty strip and looked like a missing result. How many
   frames it actually takes is reported rather than assumed. */
let stripAt = null;
for (let i = 0; i < 20; i++) {
  allRun(1);
  if (stripAt === null && allText.length) { stripAt = i + 1 }
}
const strip = allText.slice();
const allButton = (function walk(el){ return [el].concat((el.children || []).flatMap(walk)) })(allBody)
  .filter(n => n.attrs && n.attrs['data-share'])[0] || null;
if (allButton) { (allButton.handlers.click || []).forEach(fn => fn()) }
console.log(JSON.stringify({
  atLoad: atLoad, atBreak: atBreak,
  frames: allFrames,
  strip: strip, stripAt: stripAt,
  clipboard: allClipboard,
  colours: [...allColours].sort(),
  facts: { gate: gateFacts(), round: roundFacts(), skin: skinFacts(), share: shareFacts() },
  writes: [...new Set(allWrites)].sort(),
  stored: Object.keys(allStored).sort(),
}));
"""


def probe_source(
    script: str,
    *,
    speed_expr: str = "0",
    frames: int = 3800,
    stored: dict[str, object] | None = None,
    stamp: str = "2026-09-03",
) -> str:
    """One page, every feature on, one round, then the copy button."""

    payload = {
        key: (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        for key, value in (stored or {}).items()
    }
    return (
        PROBE.replace("STORED_INPUT", json.dumps(payload, ensure_ascii=False))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("STAMP_INPUT", stamp)
        .replace("SPEED_PROBE", speed_expr)
        .replace("SCRIPT_PLACEHOLDER", script)
    )


__all__ = [
    "CANVAS_WIDTH",
    "PROBE",
    "STORAGE_PREFIXES",
    "STRIP_FONT_PX",
    "key_gaps",
    "probe_source",
    "storage_keys",
    "text_width",
]
