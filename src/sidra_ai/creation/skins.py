"""A score buys a look, and never anything else.

§8 事実 6 of the play notes: the games people come back to give the time
they have already spent somewhere to go. The obvious way to build that is
also the way that ruins a game - unlock the faster ship, and everyone who
arrives later is playing a worse game than the people who arrived early.

So the rule here is narrower than "unlocks", and it is the whole point of
the item: **the only thing a cumulative score is allowed to open is a
colour.** Nothing a skin returns reaches a speed, a size, a count, a
spawn interval or the seed. The page is not asked to promise that - it is
run twice, with and without a skin, on the same seed and the same inputs,
and the two runs have to draw the *same shapes in different colours*
(``creation_cosmetic_unlock`` in scripts/product_metrics.py). A skin that
changed the game would show up as a changed geometry trace.

The total is a device-local number under ``sidra.total.<template>``,
banked by the same ``roundBank`` that already writes the personal best.
No URL, no fetch, nothing about the device - the same boundary the tuning
panel and the index sit inside.

Thresholds are per template because scores are: a good adventure round is
a handful of gems and a good puzzle round is several hundred points, so
one shared "200pt" would hand the puzzle three skins in a sitting and
never open one for the adventure. ``SKIN_UNIT`` is what one played-out
round of that template actually scores, measured with the masher rather
than guessed, and the three steps are multiples of it.
"""

from __future__ import annotations

import json

#: One mashed-out round, in that template's own score. Measured (2026-09-03)
#: by mashing each generated page for a full 60-second round and reading
#: ``roundFacts().score``; a test replays that measurement so a template
#: whose scoring changes shape cannot leave the thresholds behind.
SKIN_UNIT: dict[str, int] = {
    "adventure": 2,
    "catch": 23,
    "duel": 3,
    "fishing": 132,
    "kaiju": 3,
    "platformer": 1,
    "puzzle": 58,
    "racing": 3,
    "shooter": 74,
}

#: How many played-out rounds each skin costs. Nothing is free (a skin the
#: first round hands over is not a reason to play a second), and nothing is
#: far away enough to be theoretical.
SKIN_STEPS: tuple[int, ...] = (3, 10, 25)

#: The catalogue. Colour and name only - there is deliberately no field a
#: skin could put a number in, because a field that existed would eventually
#: be used. The first entry is the theme's own accent and costs nothing.
SKIN_COLOURS: tuple[tuple[str, str, str | None], ...] = (
    ("base", "はじまりの色", None),
    ("ember", "残り火", "#ff8a3d"),
    ("frost", "霜", "#7ad7ff"),
    ("verdant", "苔むす", "#7bd88f"),
)

#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``skinAccent`` would
#: break only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "skinTotal",
    "skinBank",
    "skinUnlocked",
    "skinChosen",
    "skinAccent",
    "skinPick",
    "skinPanel",
    "skinFacts",
    "skinNews",
)


def skin_spec(template: str) -> dict:
    """The catalogue this page ships, priced in this template's own score."""

    unit = SKIN_UNIT.get(template, 1)
    skins = [{"id": SKIN_COLOURS[0][0], "label": SKIN_COLOURS[0][1], "accent": None, "at": 0}]
    for (ident, label, accent), step in zip(SKIN_COLOURS[1:], SKIN_STEPS):
        skins.append({"id": ident, "label": label, "accent": accent, "at": unit * step})
    return {"template": template, "unit": unit, "skins": skins}


SKIN_PREAMBLE = """
/* --- cosmetic unlocks: a score buys a colour, and nothing else (§8 事実 6) */
const SKIN_SPEC=SKIN_SPEC_TOKEN;
const SKIN_TOTAL_KEY='sidra.total.'+SKIN_SPEC.template;
const SKIN_PICK_KEY='sidra.skin.'+SKIN_SPEC.template;
let SKIN_NEWS=null,SKIN_BUTTONS=[];
/* Storage is a convenience, never a dependency: a browser with it switched
   off plays the game the generator built, in the theme's own colour. */
function skinStore(){try{return (typeof localStorage!=='undefined')?localStorage:null}
  catch(e){return null}}
function skinTotal(){const s=skinStore();if(!s)return 0;
  try{const v=Number(s.getItem(SKIN_TOTAL_KEY));
    return (isFinite(v)&&v>0)?v:0}catch(e){return 0}}
function skinUnlocked(){const t=skinTotal();
  return SKIN_SPEC.skins.filter(function(k){return t>=k.at})}
/* An id that was never earned falls back to the free one. It is only a
   colour, so this is tidiness rather than a defence - but a picker that
   showed a skin as locked while the page wore it would be a lie. */
function skinChosen(){const s=skinStore();let id=null;
  try{if(s)id=s.getItem(SKIN_PICK_KEY)}catch(e){}
  const hit=skinUnlocked().filter(function(k){return k.id===id})[0];
  return hit||SKIN_SPEC.skins[0]}
/* The one thing a skin returns. Every number the game plays by is read
   before this line and none of them through it - which is what the judge
   checks by running the page twice and comparing what was drawn where. */
function skinAccent(fallback){const k=skinChosen();
  return (k&&typeof k.accent==='string'&&/^#[0-9a-fA-F]{6}$/.test(k.accent))
    ?k.accent:fallback}
/* Banked by roundBank, once per round, with the round's own score. */
function skinBank(points){if(typeof points!=='number'||!isFinite(points)||points<=0){
    return skinTotal()}
  const before=skinUnlocked().length,next=skinTotal()+points,s=skinStore();
  try{if(s)s.setItem(SKIN_TOTAL_KEY,String(next))}catch(e){}
  const opened=skinUnlocked();
  if(opened.length>before){SKIN_NEWS=opened[opened.length-1].label}
  return next}
function skinNews(){return SKIN_NEWS}
function skinReload(){try{if(typeof location!=='undefined'&&location
  &&typeof location.reload==='function'){location.reload()}}catch(e){}}
function skinPick(id){const hit=skinUnlocked().filter(function(k){return k.id===id})[0];
  if(!hit)return false;
  const s=skinStore();try{if(s)s.setItem(SKIN_PICK_KEY,hit.id)}catch(e){}
  skinReload();return true}
function skinPanel(){
  if(typeof document==='undefined'||!document.createElement)return null;
  const host=(document.querySelector&&document.querySelector('main'))||document.body;
  if(!host||!host.appendChild)return null;
  const box=document.createElement('details');box.id='skin';
  box.style.cssText='margin:12px 0 0;padding:10px 14px;border:1px solid BORDER_TOKEN;'
    +'border-radius:6px;font-size:13px';
  const sum=document.createElement('summary');
  sum.textContent='見た目（累計 '+skinTotal()+'）';
  sum.style.cssText='cursor:pointer';box.appendChild(sum);
  const note=document.createElement('p');
  note.textContent='遊んだぶんだけ色が増えます。強さは変わりません。';
  note.style.cssText='margin:6px 0;opacity:0.75';box.appendChild(note);
  const chosen=skinChosen(),open=skinUnlocked();
  SKIN_SPEC.skins.forEach(function(k){
    const earned=open.filter(function(o){return o.id===k.id}).length>0;
    const b=document.createElement('button');b.type='button';
    b.setAttribute('data-skin',k.id);
    b.textContent=earned?(k.label+(k.id===chosen.id?' ✓':''))
      :(k.label+'（あと '+(k.at-skinTotal())+'）');
    if(!earned){b.disabled=true}
    b.style.cssText='margin:2px 6px 2px 0;padding:4px 10px;border-radius:4px;'
      +'border:1px solid BORDER_TOKEN;cursor:'+(earned?'pointer':'default');
    b.addEventListener('click',function(){skinPick(k.id)});
    SKIN_BUTTONS.push(b);box.appendChild(b)});
  host.appendChild(box);return box}
/* What the judge reads back after driving the real buttons. */
function skinFacts(){return {template:SKIN_SPEC.template,total:skinTotal(),
  unit:SKIN_SPEC.unit,
  unlocked:skinUnlocked().map(function(k){return k.id}),
  locked:SKIN_SPEC.skins.filter(function(k){return skinTotal()<k.at})
    .map(function(k){return {id:k.id,at:k.at}}),
  current:skinChosen().id,accent:skinAccent(null),news:SKIN_NEWS,
  buttons:SKIN_BUTTONS.length}}
if(typeof document!=='undefined'&&document.addEventListener&&document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',skinPanel)}else{skinPanel()}
/* --- end cosmetic unlocks --- */
"""


def preamble_for(template: str) -> str:
    """The catalogue, priced for one template."""

    return SKIN_PREAMBLE.replace(
        "SKIN_SPEC_TOKEN", json.dumps(skin_spec(template), ensure_ascii=False)
    )


#: The only three places the rest of the page is allowed to touch the skin,
#: and what each one is for. The behavioural trace can only see an axis the
#: masher actually exercises, and it cannot exercise all of them - so the
#: same claim is made a second way, by reading the assembled page: if
#: nothing outside these three call sites can reach a skin, a skin cannot
#: reach a number.
#: The preamble's own bounds in the assembled page. Sliced by these rather
#: than by comparing against ``preamble_for`` output, because by the time the
#: page exists the theme tokens inside it have been substituted.
SKIN_OPEN = "/* --- cosmetic unlocks:"
SKIN_CLOSE = "/* --- end cosmetic unlocks --- */"

SANCTIONED_CALLS: dict[str, str] = {
    "skinAccent(": "the colour the page paints with (tuning.py)",
    "skinBank(": "the round's score, added to the total (round.py)",
    "skinNews(": "the line that says a colour opened (round.py)",
}


def stray_calls(script: str, template: str) -> list[str]:
    """Every reach into the skin from outside its own preamble.

    ``script`` is the whole assembled page script. The skin's own preamble
    is removed first - it is allowed to call itself - and what remains is
    every other preamble and the template body.
    """

    start = script.find(SKIN_OPEN)
    stop = script.find(SKIN_CLOSE)
    if start < 0 or stop < 0:
        return ["the skin preamble is not in the page"]
    rest = script[:start] + script[stop + len(SKIN_CLOSE) :]
    stray = []
    for name in PREAMBLE_NAMES:
        call = name + "("
        seen = rest.count(call)
        allowed = 1 if call in SANCTIONED_CALLS else 0
        if seen > allowed:
            stray.append(f"{call} called {seen} time(s), {allowed} sanctioned")
    return stray


#: Plays a whole round with a masher, recording *what was drawn where* and
#: *in what colour* separately. The claim needs both: the same shapes prove
#: the game did not change, and different colours prove the skin did
#: something. ``Math.random`` and ``Date`` are pinned, or two runs would
#: diverge for reasons that have nothing to do with skins.
PROBE = """
const skinNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : skinNothing),
  apply: () => skinNothing, set: () => true });
let skinRnd = 2463534242;
Math.random = () => { skinRnd ^= skinRnd << 13; skinRnd ^= skinRnd >>> 17;
  skinRnd ^= skinRnd << 5; return ((skinRnd >>> 0) % 100000) / 100000 };
class SkinDate {
  constructor(){ return SkinDate.parse() }
  static parse(){ const [y, m, d] = '2026-09-03'.split('-').map(Number);
    return { getFullYear: () => y, getMonth: () => m - 1, getDate: () => d } }
}
globalThis.Date = SkinDate;
globalThis.matchMedia = () => ({ matches: false });
let skinClock = 0;
globalThis.performance = { now: () => skinClock };
const skinKeys = [], skinUps = [], skinPointers = [];
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') skinKeys.push(fn);
  if (type === 'keyup') skinUps.push(fn) };
globalThis.Image = function(){ return skinNothing };
const skinStored = STORED_INPUT;
let skinWrites = 0, skinReloads = 0;
globalThis.localStorage = {
  getItem: (k) => (k in skinStored ? skinStored[k] : null),
  setItem: (k, v) => { skinWrites++; skinStored[k] = String(v) },
  removeItem: (k) => { delete skinStored[k] } };
globalThis.location = { reload: () => { skinReloads++ } };
/* Two traces, kept apart on purpose. */
let skinGeometry = 2166136261;
const skinColours = new Set(), skinText = [];
function skinHash(value){ const s = String(value);
  for (let i = 0; i < s.length; i++) {
    skinGeometry ^= s.charCodeAt(i);
    skinGeometry = Math.imul(skinGeometry, 16777619) >>> 0 } }
function skinContext(){
  const rec = {
    set fillStyle(v){ if (typeof v === 'string') skinColours.add(v.toLowerCase()) },
    get fillStyle(){ return '' },
    set strokeStyle(v){ if (typeof v === 'string') skinColours.add(v.toLowerCase()) },
    get strokeStyle(){ return '' },
    fillRect(...a){ skinHash('R' + a.map(n => Math.round(Number(n) * 100)).join(',')) },
    strokeRect(...a){ skinHash('S' + a.map(n => Math.round(Number(n) * 100)).join(',')) },
    drawImage(...a){ skinHash('I' + a.slice(1).map(n => Math.round(Number(n) * 100)).join(',')) },
    fillText(t, x, y){ skinText.push(String(t));
      skinHash('T' + String(t) + ',' + Math.round(Number(x)) + ',' + Math.round(Number(y))) },
  };
  return new Proxy(rec, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : skinNothing)),
    set: (t, k, v) => { if (k in t) { t[k] = v } return true } }) }
const skinCtx = skinContext();
const skinCanvas = { width: 720, height: 320, style: {},
  addEventListener: (type, fn) => { if (type === 'pointerdown') skinPointers.push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => skinCtx };
function skinElement(tag){
  const el = { tagName: tag, style: {}, children: [], attrs: {}, handlers: {}, disabled: false,
    appendChild(c){ this.children.push(c); return c },
    setAttribute(k, v){ this.attrs[k] = v },
    getAttribute(k){ return this.attrs[k] },
    addEventListener(name, fn){ (this.handlers[name] = this.handlers[name] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => skinCtx, width: 720, height: 320 };
  return el }
const skinBody = skinElement('body');
globalThis.document = { readyState: 'complete', body: skinBody,
  createElement: skinElement, querySelector: () => null,
  getElementById: () => skinCanvas };
let skinQueued = null;
globalThis.requestAnimationFrame = (fn) => { skinQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function skinPress(key, code){
  const ev = { key: key, code: code, clientX: 360, clientY: 160,
    pointerType: 'touch', pointerId: 1,
    preventDefault(){}, stopImmediatePropagation(){} };
  skinKeys.forEach(fn => fn(ev));
  return ev }
function skinRelease(ev){ skinUps.forEach(fn => fn(ev)) }
function skinTap(){ skinPointers.forEach(fn => fn({ pointerType: 'touch', pointerId: 1,
  clientX: 340, clientY: 150, preventDefault(){}, stopImmediatePropagation(){} })) }
skinRelease(skinPress(' ', 'Space'));
/* All four, so the run covers as much of each game as a masher can. It is
   still only as much as a masher can: breaking the wiring on purpose
   showed that the adventure keeps every enemy it has in a room this
   player never reaches, so its speed axis is never exercised here and
   the traces would not notice a skin that moved it. That gap is why the
   judge also reads the assembled page for *who calls the skin at all* -
   the two checks fail in different ways, which is the point of having
   both. */
const SKIN_DIRS = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'];
let skinHeld = null, skinDone = false;
const skinScores = [];
/* One round, and it stops when that round ends. Several templates restart
   on the action key or on a tap, so a masher that kept going would bank
   two rounds in one load and the price of a colour would be measured
   against the wrong thing. */
for (let f = 0; f < FRAMES_INPUT && skinQueued && !skinDone; f++) {
  if (f % 30 === 0) {
    if (skinHeld) { skinRelease(skinHeld) }
    const dir = SKIN_DIRS[(f / 30) % SKIN_DIRS.length];
    skinHeld = skinPress(dir, dir) }
  if (f % 15 === 0) { skinRelease(skinPress(' ', 'Space')); skinTap() }
  const fn = skinQueued; skinQueued = null;
  skinClock += 50 / 3;
  fn(skinClock);
  if (f % 300 === 0) { skinScores.push(roundFacts().live) }
  const now = roundFacts();
  if (f > 60 && (now.done || now.ended)) { skinDone = true }
}
/* Two more frames, untouched, so the strip draws and the round is banked. */
for (let i = 0; i < 2 && skinQueued; i++) {
  const fn = skinQueued; skinQueued = null;
  skinClock += 50 / 3;
  fn(skinClock);
}
/* The picker the page built, walked rather than remembered. */
function skinFlatten(el){ return [el].concat((el.children || []).flatMap(skinFlatten)) }
const skinNodes = skinFlatten(skinBody);
const skinPanelNode = skinNodes.filter(n => n.id === 'skin')[0] || null;
const skinPickers = skinNodes.filter(n => n.attrs && n.attrs['data-skin']);
let skinPicked = null;
if (PICK_INPUT) {
  const target = skinPickers.filter(n => n.getAttribute('data-skin') === PICK_INPUT)[0];
  if (target && !target.disabled) {
    (target.handlers.click || []).forEach(fn => fn());
    skinPicked = skinStored['sidra.skin.' + SKIN_SPEC.template] || null } }
console.log(JSON.stringify({
  geometry: skinGeometry, colours: [...skinColours].sort(), scores: skinScores,
  said: skinText.slice(-8),
  accent: TUNE_ACCENT,
  facts: skinFacts(), round: roundFacts(),
  panel: !!skinPanelNode,
  pickers: skinPickers.map(n => ({ id: n.getAttribute('data-skin'), locked: !!n.disabled })),
  picked: skinPicked,
  storedTotal: skinStored['sidra.total.' + SKIN_SPEC.template] || null,
  reloads: skinReloads,
}));
"""


def probe_source(
    script: str,
    *,
    frames: int = 3800,
    stored: dict[str, object] | None = None,
    pick: str | None = None,
) -> str:
    """The page, played out by a masher, watched by two separate traces."""

    payload = {
        key: (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        for key, value in (stored or {}).items()
    }
    return (
        PROBE.replace("STORED_INPUT", json.dumps(payload, ensure_ascii=False))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("PICK_INPUT", json.dumps(pick))
        .replace("SCRIPT_PLACEHOLDER", script)
    )


__all__ = [
    "PREAMBLE_NAMES",
    "SANCTIONED_CALLS",
    "SKIN_CLOSE",
    "SKIN_OPEN",
    "PROBE",
    "SKIN_COLOURS",
    "SKIN_PREAMBLE",
    "SKIN_STEPS",
    "SKIN_UNIT",
    "preamble_for",
    "probe_source",
    "skin_spec",
    "stray_calls",
]
