"""One line a person can paste, that gives nothing away.

§8 事実 7: what spreads a game is a result its player wants to show, and
what makes showing it safe for everybody else is that the result cannot
be read backwards into the answer. The pattern the whole genre settled on
is a row of emoji: it says how the round went and nothing about how the
board was laid out.

Three things are deliberately *not* in the line, and each is a rule
rather than an oversight:

* **No URL.** The artifact is a file on a disk that talks to nothing;
  a link in the share text would be a link to something that does not
  exist, or worse, to something that does.
* **Nothing about the person.** Not the title (which is made out of the
  words *they* typed into the request), not the device, not the locale,
  not the time of day. The template's own genre name is used instead -
  it is the same for everyone who ever built this template.
* **Nothing about the board.** Above all not the seed. The daily stamp is
  safe because it is the same for everybody that day, which is the whole
  point of C-1107; the request-derived seed is the opposite of that.

Copying is ``navigator.clipboard.writeText`` with the old textarea trick
behind it, and nothing else - no share sheet, no network, no analytics.
"""

from __future__ import annotations

from sidra_ai.creation.probekit import seed_store

import json
import math

from sidra_ai.creation.skins import SKIN_UNIT

#: The template's own genre, never the generated title. The title is built
#: out of the words the person typed, so it is theirs; this is not.
SHARE_NAME: dict[str, str] = {
    "adventure": "探索",
    "catch": "キャッチ",
    "duel": "対戦",
    "fishing": "釣り",
    "kaiju": "巨獣戦",
    "marble": "玉転がし",
    "platformer": "跳躍",
    "puzzle": "パズル",
    "racing": "レース",
    "shooter": "シューティング",
}

#: One character standing for the thing the score counts. A row of these
#: is the whole result: it has a size, and no shape.
SHARE_EMOJI: dict[str, str] = {
    "adventure": "💎",
    "catch": "🧺",
    "duel": "⚔️",
    "fishing": "🐟",
    "kaiju": "👊",
    "marble": "🔷",
    "platformer": "💠",
    "puzzle": "🧩",
    "racing": "🏁",
    "shooter": "💥",
}

#: The row never grows past this. A puzzle round scoring several hundred
#: would otherwise paste as several hundred characters.
SHARE_MAX = 10

#: How many of the row a typical round fills. Five of ten, so a good round
#: reads as "better than usual" without the row ever being all-or-nothing.
SHARE_TYPICAL = 5


def share_spec(template: str, *, in_japanese: bool = True) -> dict:
    """What one page needs to write its own line.

    The genre's English comes from ``vocabulary.english_label_for`` rather
    than from a second table here (C-1930, C-1965): the page already has a
    place where a template's English name lives.
    """

    from sidra_ai.creation.vocabulary import english_label_for

    unit = SKIN_UNIT.get(template, 1)
    return {
        "template": template,
        "name": (
            SHARE_NAME.get(template, "ゲーム")
            if in_japanese
            else english_label_for(template)
        ),
        "emoji": SHARE_EMOJI.get(template, "⭐"),
        # One emoji per this much score, so a mashed-out round fills about
        # half the row. Never zero: a template whose round scores 1 would
        # divide by nothing.
        "per": max(1, round(unit / SHARE_TYPICAL)),
        "max": SHARE_MAX,
    }


def bar_for(score: float | None, spec: dict) -> str:
    """The row the page itself would draw, by the page's own rule.

    Anything checking the row has to re-derive it from the score - a
    judge that reads the count off the page it is judging agrees with
    itself. But re-deriving it in Python is where C-1437 came from:
    ``shareBar()`` counts with JS ``Math.round``, which sends a half up,
    and Python's ``round`` sends a half to the nearest *even*. They agree
    everywhere except when ``score / per`` lands exactly halfway, and
    then the page is called wrong for being right.

    It surfaced when a scoring change put one round on the tie (puzzle,
    daily on, per=12, score 78 -> 6.5): the page drew 7, the checker
    wanted 6, and a green judge went to 0. Nothing about that was the
    page's fault, and the tie is reachable by any template whose points
    ever move, so the mirror lives here, once, rather than being written
    out again at each place that needs it.

    ``Math.round(x)`` is specified as ``floor(x + 0.5)``, so that is what
    the mirror is. (The negative-zero corner of that definition cannot be
    reached: a row is only drawn for a score above zero.)
    """

    if not (score and score > 0):
        return ""
    n = max(1, min(spec["max"], math.floor(score / spec["per"] + 0.5)))
    return spec["emoji"] * n


#: Names the preamble introduces, held to by a test like the other
#: preambles'.
PREAMBLE_NAMES: tuple[str, ...] = (
    "shareText",
    "shareTuned",
    "shareCopy",
    "shareReady",
    "shareBar",
    "shareScore",
    "shareFacts",
)

SHARE_PREAMBLE = """
/* --- the line you can paste (§8 事実 7) ------------------------------- */
const SHARE_SPEC=SHARE_SPEC_TOKEN;
let SHARE_LAST=null,SHARE_COPIES=0,SHARE_BUTTON=null;
/* A round is worth sharing once it is over - by the clock or by the
   template's own ending. Before that there is no result to talk about. */
function shareReady(){try{return (ROUND_DONE||roundEnded())&&shareScore()!==null}
  catch(e){return false}}
/* The round that ended, not the frame this happens to be. A template that
   restarts in place has already zeroed its counter by the time anybody
   reaches for the button, so the banked figure is the only honest one. */
function shareScore(){try{
  if(ROUND_FINAL!==null&&ROUND_FINAL!==undefined)return ROUND_FINAL;
  return roundScore()}catch(e){return null}}
/* Size, and no shape. The row says how the round went; it cannot be read
   backwards into where anything was. */
function shareBar(score){
  if(!(score>0))return '';
  const n=Math.max(1,Math.min(SHARE_SPEC.max,Math.round(score/SHARE_SPEC.per)));
  let out='';for(let i=0;i<n;i++){out+=SHARE_SPEC.emoji}
  return out}
/* What this player changed about the board itself (C-1768). §8 事実 7
   records why Wordle's sharing worked: a spoiler-free boast about a
   challenge EVERYBODY GOT. The stamp below used to be written on the
   strength of the seed alone - and the seed is only half of the board.
   The panel holds the other half, so two people could paste the same
   date over two different games: measured, with one seed and one date,
   catch scored 15 against 40, fishing 49 against 122, puzzle laid out
   10 columns against 14.
   Said rather than taken away: forcing the ladder back for a daily run
   would silently undo a control the player used, which is the harm
   C-1729 and C-1764 are about.
   Compared by VALUE, and only the two axes. Setting a dial back to where
   it started changes nothing and deserves no caveat. The difficulty row
   is deliberately not a third thing to name: picking a preset writes
   speed and band (tuneSet), so the axes already say what moved and by
   how much - while a stored rung on its own moves no axis at all, and
   naming it claimed a changed board for a board that had not changed.
   Measured both ways: the preset scored 61 against 78 and is named; the
   bare rung scored 78, the same as untouched, and is not.
   Nothing here is the player's own words, the title or the seed: labels
   are the product's, numbers come from the author's own span, so
   `leaks()` has nothing new to find. */
function shareTuned(){
  const out=[];
  try{['speed','band'].forEach(function(k){
    const f=tuneField(k);if(!f)return;
    const v=tuneNum(k,f.default);
    if(v!==f.default)out.push(f.label+' '+v)})}catch(e){}
  return out}
function shareText(){
  if(!shareReady())return null;
  const score=shareScore();
  /* The daily stamp is the same for everybody who played today ONLY when
     the board is the one this page opens with - see shareTuned. The
     request-derived seed is the opposite and never appears. */
  let head=SHARE_SPEC.name;
  try{if(dailyBoard()){head=CW.todays+SHARE_SPEC.name+' '+dailyStamp();
    const marks=shareTuned();
    /* The other runtime source of a diverged daily board (C-1777): adapt's
       auto-ease (three losses buy one easier rung, C-1402). It is not a
       hand-set value, so shareTuned() never sees it - but the board it
       produced is easier than the one everybody else got, which is exactly
       the "challenge everybody got" claim C-1768 exists to protect. Read
       ADAPT_EASED (set when adaptSpeed stepped the speed down at load, and
       still true after the win that clears the streak), so a run played on
       the eased board is not pasted as the standard daily. */
    try{if(typeof adaptFacts==='function'&&adaptFacts().eased)marks.push(CW.auto_eased)}catch(e){}
    if(marks.length)head+=CW.note_open+marks.join(CW.mark_join)+CW.note_close}}catch(e){}
  const bar=shareBar(score);
  let line=head+(bar?(' '+bar):'')+' '+ROUND_LABEL+' '+score;
  /* Only when there is something to have been best at: a first run that
     scored nothing is not a record, whatever the comparison says. */
  try{if(ROUND_RECORD&&score>0){line+=CW.personal_best}}catch(e){}
  return line}
/* The clipboard, and nothing else. No share sheet, no link, no request. */
function shareWrite(text){
  try{if(typeof navigator!=='undefined'&&navigator&&navigator.clipboard
    &&typeof navigator.clipboard.writeText==='function'){
      navigator.clipboard.writeText(text);return true}}catch(e){}
  try{const box=document.createElement('textarea');box.value=text;
    document.body.appendChild(box);
    if(box.select){box.select()}
    if(document.execCommand){document.execCommand('copy')}
    if(box.remove){box.remove()}
    return true}catch(e){}
  return false}
function shareCopy(){const text=shareText();
  if(text===null)return null;
  SHARE_LAST=text;SHARE_COPIES++;shareWrite(text);
  if(SHARE_BUTTON){SHARE_BUTTON.textContent=CW.copied}
  return text}
addEventListener('keydown',function(e){
  if((e.key==='c'||e.key==='C')&&shareReady()){shareCopy()}});
function sharePanel(){
  if(typeof document==='undefined'||!document.createElement)return null;
  const host=(document.querySelector&&document.querySelector('main'))||document.body;
  if(!host||!host.appendChild)return null;
  const b=document.createElement('button');b.type='button';
  b.setAttribute('data-share','copy');
  b.textContent=CW.copy_result;
  b.style.cssText='margin:12px 0 0;padding:6px 14px;border-radius:4px;font-size:13px;'
    +'border:1px solid BORDER_TOKEN;cursor:pointer';
  b.addEventListener('click',shareCopy);
  SHARE_BUTTON=b;host.appendChild(b);return b}
/* What the judge reads back after pressing the page's own button. */
function shareFacts(){return {template:SHARE_SPEC.template,ready:shareReady(),
  text:shareText(),last:SHARE_LAST,copies:SHARE_COPIES,
  score:shareScore(),bar:shareBar(shareScore()),
  emoji:SHARE_SPEC.emoji,per:SHARE_SPEC.per,max:SHARE_SPEC.max}}
if(typeof document!=='undefined'&&document.addEventListener&&document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',sharePanel)}else{sharePanel()}
/* --- end the line you can paste --- */
"""


def preamble_for(template: str, *, in_japanese: bool = True) -> str:
    """The line, told what this template counts and calls itself."""

    return SHARE_PREAMBLE.replace(
        "SHARE_SPEC_TOKEN",
        json.dumps(share_spec(template, in_japanese=in_japanese), ensure_ascii=False),
    )


#: Everything a shared line must never contain. Checked against the string
#: the page actually put on the clipboard, not against the source.
BANNED_IN_TEXT: tuple[str, ...] = (
    "http",
    "://",
    "www.",
    "@",
    "localhost",
    "127.0.0.1",
    "file:",
)


def leaks(text: str, *, request: str, title: str, seed: int) -> list[str]:
    """Everything in a shared line that should not be there.

    ``request`` and ``title`` are the person's own words; ``seed`` is the
    board. A line carrying any of them is not spoiler-free and not
    anonymous, whatever else it says.
    """

    found = [f"contains {banned!r}" for banned in BANNED_IN_TEXT if banned in text]
    if str(seed) in text:
        found.append("contains the seed")
    if title and title in text:
        found.append("contains the generated title")
    for word in request.split():
        if len(word) >= 3 and word in text:
            found.append(f"contains the request word {word!r}")
    return found


#: Plays a round out, then presses the page's own copy button and reads
#: what reached the clipboard. Grepping the source for 'clipboard' would
#: say nothing about what the string contains.
PROBE = """
const shareNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : shareNothing),
  apply: () => shareNothing, set: () => true });
let shareRnd = 2463534242;
Math.random = () => { shareRnd ^= shareRnd << 13; shareRnd ^= shareRnd >>> 17;
  shareRnd ^= shareRnd << 5; return ((shareRnd >>> 0) % 100000) / 100000 };
class ShareDate {
  constructor(){ return ShareDate.parse() }
  static parse(){ const [y, m, d] = 'STAMP_INPUT'.split('-').map(Number);
    return { getFullYear: () => y, getMonth: () => m - 1, getDate: () => d } }
}
globalThis.Date = ShareDate;
globalThis.matchMedia = () => ({ matches: false });
let shareClock = 0;
globalThis.performance = { now: () => shareClock };
const shareKeys = [], shareUps = [], sharePointers = [];
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') shareKeys.push(fn);
  if (type === 'keyup') shareUps.push(fn) };
globalThis.Image = function(){ return shareNothing };
const shareStored = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in shareStored ? shareStored[k] : null),
  setItem: (k, v) => { shareStored[k] = String(v) },
  removeItem: (k) => { delete shareStored[k] } };
globalThis.location = { reload: () => {} };
/* The clipboard, recorded rather than swallowed: the claim is about the
   characters that reach it. */
const shareClipboard = [];
/* defineProperty, not assignment: node ships its own read-only `navigator`,
   and a plain assignment is dropped without a word - which looked exactly
   like a page that never copied anything. */
Object.defineProperty(globalThis, 'navigator', { configurable: true, writable: true,
  value: { clipboard: {
    writeText: (t) => { shareClipboard.push(String(t)); return { then: () => {} } } } } });
const shareDrawn = [], shareFallback = [];
const shareCtx = new Proxy({ fillText: (t) => { shareDrawn.push(String(t)) } }, {
  get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : shareNothing)),
  set: () => true });
const shareCanvas = { width: 720, height: 320, style: {},
  addEventListener: (type, fn) => { if (type === 'pointerdown') sharePointers.push(fn) },
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => shareCtx };
function shareElement(tag){
  const el = { tagName: tag, style: {}, children: [], attrs: {}, handlers: {},
    value: '', appendChild(c){ this.children.push(c); return c },
    remove(){}, select(){},
    setAttribute(k, v){ this.attrs[k] = v },
    getAttribute(k){ return this.attrs[k] },
    addEventListener(name, fn){ (this.handlers[name] = this.handlers[name] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => shareCtx, width: 720, height: 320 };
  return el }
const shareBody = shareElement('body');
globalThis.document = { readyState: 'complete', body: shareBody,
  createElement: shareElement, querySelector: () => null,
  execCommand: () => { shareBody.children.filter(n => n.tagName === 'textarea')
    .forEach(n => shareFallback.push(String(n.value))); return true },
  getElementById: () => shareCanvas };
let shareQueued = null;
globalThis.requestAnimationFrame = (fn) => { shareQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function sharePress(key, code){
  const ev = { key: key, code: code, clientX: 360, clientY: 160,
    pointerType: 'touch', pointerId: 1,
    preventDefault(){}, stopImmediatePropagation(){} };
  shareKeys.forEach(fn => fn(ev));
  return ev }
function shareRelease(ev){ shareUps.forEach(fn => fn(ev)) }
function shareTap(){ sharePointers.forEach(fn => fn({ pointerType: 'touch', pointerId: 1,
  clientX: 340, clientY: 150, preventDefault(){}, stopImmediatePropagation(){} })) }
shareRelease(sharePress(' ', 'Space'));
const SHARE_DIRS = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'];
let shareHeld = null, shareEarly = { ready: false, text: null },
  shareFrames = 0, shareEnded = false;
/* Play until the round ends, then stop touching anything. Several
   templates restart on the action key or on a tap, so a masher that kept
   going would be asking for the score of a round it began by accident -
   which is exactly how the first version of this probe came back with a
   zero for the kaiju. A person copies the result that is on the screen. */
for (let f = 0; f < FRAMES_INPUT && shareQueued && !shareEnded; f++) {
  if (f % 30 === 0) {
    if (shareHeld) { shareRelease(shareHeld) }
    const dir = SHARE_DIRS[(f / 30) % SHARE_DIRS.length];
    shareHeld = sharePress(dir, dir) }
  if (f % 15 === 0) { shareRelease(sharePress(' ', 'Space')); shareTap() }
  const fn = shareQueued; shareQueued = null;
  shareClock += 50 / 3;
  fn(shareClock);
  shareFrames = f + 1;
  /* While the round is live, pressing copy must produce nothing at all:
     a button that answered mid-round would be sharing a number nobody
     finished scoring. Checked on every live frame rather than at a fixed
     one-second mark - that checkpoint assumed the round was "certainly
     running", and a run that dies in under a second (a marble held into
     the first block does) ends before it, so the checkpoint would read
     the finished, legitimately copyable result as a mid-round leak. */
  const now = roundFacts();
  if (!now.done && !now.ended && (shareReady() || shareText() !== null)) {
    shareEarly = { ready: shareReady(), text: shareText() } }
  if (f > 60 && (now.done || now.ended)) { shareEnded = true }
}
/* Two more frames, untouched, so the result strip draws and the round is
   banked - the same thing that happens while a person reads it. */
for (let i = 0; i < 2 && shareQueued; i++) {
  const fn = shareQueued; shareQueued = null;
  shareClock += 50 / 3;
  fn(shareClock);
}
function shareFlatten(el){ return [el].concat((el.children || []).flatMap(shareFlatten)) }
const shareNodes = shareFlatten(shareBody);
const shareButton = shareNodes.filter(n => n.attrs && n.attrs['data-share'])[0] || null;
if (shareButton) { (shareButton.handlers.click || []).forEach(fn => fn()) }
const shareAfterClick = shareClipboard.slice();
/* And the keyboard, which is the same act by another route. */
sharePress('c', 'KeyC');
console.log(JSON.stringify({
  facts: shareFacts(), round: roundFacts(),
  early: shareEarly,
  button: !!shareButton,
  buttonLabel: shareButton ? shareButton.textContent : null,
  clipboard: shareClipboard, afterClick: shareAfterClick,
  fallback: shareFallback,
  drawn: shareDrawn.slice(-8),
  running: shareQueued !== null, frames: shareFrames, ended: shareEnded,
}));
"""


def probe_source(
    script: str,
    *,
    frames: int = 3800,
    stored: dict[str, object] | None = None,
    stamp: str = "2026-09-03",
) -> str:
    """The page, played out and then asked for its line."""

    payload = seed_store(stored)
    return (
        PROBE.replace("STORED_INPUT", json.dumps(payload, ensure_ascii=False))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("STAMP_INPUT", stamp)
        .replace("SCRIPT_PLACEHOLDER", script)
    )


__all__ = [
    "BANNED_IN_TEXT",
    "PREAMBLE_NAMES",
    "PROBE",
    "SHARE_EMOJI",
    "SHARE_MAX",
    "SHARE_NAME",
    "SHARE_PREAMBLE",
    "SHARE_TYPICAL",
    "leaks",
    "preamble_for",
    "probe_source",
    "share_spec",
]
