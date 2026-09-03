"""A title screen, so nobody is playing before they have read anything.

Every template started the moment the page loaded. On a desktop that costs a
few seconds of confusion; on a phone the instructions sit below the fold, so
the player never sees them at all and the first thing that happens is losing
a life. It also meant the first sound arrived with no user gesture behind it,
which browsers refuse - the audio unlocked on some later keypress, or never.

One press fixes all three: it is the gesture that unlocks the AudioContext,
the moment the instructions have been on screen, and the start of the game.

The mechanism is the one the other shared preambles use - wrap
``requestAnimationFrame`` once - with one ordering fact behind it. Each
wrapper's own work runs *after* the wrapper installed later, because later
wrappers end up nested inside. So the gate is installed **first**, which puts
its overlay on top of the pad and the particles rather than under them. The
same fact means the juice preamble's particles draw over the touch pad; that
is fine, and it is the opposite of what C-1020's note claimed.

While the gate is closed the template's own callback is never called - the
game cannot advance a frame it has not been given - and the loop keeps
re-scheduling itself, exactly as the hitstop does.
"""

from __future__ import annotations

#: What the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "gateState",
    "gateFrames",
    "gateBrief",
    "gateSkipped",
    "gateSeen",
    "gateGesture",
    "gateFacts",
)

#: The three lines the title screen prints before anyone presses anything:
#: what you are trying to do, what you press, and what is in your way.
#:
#: The owner's viewing notes (§6 観察 3) start their escalation with a
#: briefing table - the scene exists so the audience knows the objective
#: before the shooting starts, and it is the reason the shooting reads as
#: something going wrong rather than as noise. A title plus a control list
#: says which buttons exist; it does not say what you are *for*.
#:
#: Kept per template because a shared sentence would be the tell that nobody
#: wrote one: "敵を倒す" over a fishing game is worse than no line at all.
#: The control line is checked against ``story.CONTROLS`` by the tests rather
#: than copied from it - two tables of the same fact drift, and the one that
#: drifts is the one nobody reads.
BRIEFINGS: dict[str, tuple[str, str, str]] = {
    "fishing": (
        "帯の中でタイミングを合わせ、釣果を伸ばす",
        "SPACE / タップで合わせる",
        "帯は狭く、マーカーは休まない",
    ),
    "catch": (
        "落ちてくるものを受け皿で拾い切る",
        "← → / マウスで受け皿を動かす",
        "落下は止まらず、取りこぼしは戻らない",
    ),
    "adventure": (
        "鍵を見つけ、宝箱まで辿り着く",
        "矢印 / WASD で歩き、SPACE で斬る",
        "うろつく敵と、道を塞ぐ岩と茂み",
    ),
    "duel": (
        "溜めて撃ち、相手の体力を先に削り切る",
        "SPACE 長押しで溜め、離して発射、↑ ↓ で回避",
        "早撃ち型か溜め型の相手（画面に出る）",
    ),
    "shooter": (
        "降りてくる波を落とし切る",
        "← → で移動、SPACE で連射",
        "波は速くなる。3 回ぶつかると終わり",
    ),
    "puzzle": (
        "同じ色のかたまりを消し、盤面を片づける",
        "← ↑ → ↓ でカーソル、SPACE で消す",
        "2 個未満は消せない。手が尽きたら終わり",
    ),
    "kaiju": (
        "脚を撃ち抜き、下りてきた頭を叩く。3 周期で仕留める",
        "← → で歩き、SPACE で撃つ",
        "巨獣の一撃と、走る地割れ（線が予兆）",
    ),
    "racing": (
        "コースに沿って 3 周を走り切り、タイムを残す",
        "← → でハンドルを切る",
        "路上の障害物とコース外。どちらも減速（リタイアは無い）",
    ),
    "platformer": (
        "足場を渡り、ゴールの旗まで灯りを運ぶ",
        "← → で走り、↑ / SPACE でジャンプ（長押しで高く）",
        "底なしの隙間。落ちても灯籠まで戻るだけ",
    ),
}

GATE_PREAMBLE = """
/* --- start screen and pause (installed first: its overlay draws last) --- */
const GCV=document.getElementById('stage');
const GTITLE=TITLE_TOKEN,GHOW=HOWTO_TOKEN,GBRIEF=BRIEF_TOKEN;
let GATE='title',GATE_RAN=0,GATE_SKIPPED=false,GATE_GESTURE=false;
const GATE_SEEN_KEY='sidra.seen.'+GATE_NAME_TOKEN;
function gateState(){return GATE}
function gateFrames(){return GATE_RAN}
function gateBrief(){return GBRIEF}
function gateSkipped(){return GATE_SKIPPED}
function gateStore(){try{return (typeof localStorage!=='undefined')?localStorage:null}
  catch(e){return null}}
function gateSeen(){const s=gateStore();
  try{return !!(s&&s.getItem(GATE_SEEN_KEY))}catch(e){return false}}
function gateRemember(){const s=gateStore();
  try{if(s)s.setItem(GATE_SEEN_KEY,'1')}catch(e){}}
/* The gesture the AudioContext has been waiting for. Kept apart from
   starting, because a page that opened straight into play (C-1111) has had
   no gesture yet - and a sound played without one is a sound the browser
   refuses and the player learns the game does not have. */
function gateGesture(){if(GATE_GESTURE)return;GATE_GESTURE=true;
  try{sfx('step')}catch(e){}}
function gateStart(){if(GATE==='playing')return;
  GATE='playing';gateRemember();gateGesture()}
function gateTogglePause(){if(GATE==='title')return;
  GATE=GATE==='paused'?'playing':'paused'}
/* Second visit onward, the briefing is not news. It is skipped before the
   first frame - so there is nothing to press through - unless the player
   asked to see it every time in 調整. The first visit is never skipped:
   the three lines are what the controls *are*. */
if(gateSeen()&&!tuneFlag('brief',false)){GATE='playing';GATE_SKIPPED=true}
addEventListener('keydown',e=>{
  /* Pause belongs to a game that has started. On the title screen P is
     just another key, because "any key" has to mean any key - a player
     who reaches for P first was getting nothing at all. */
  if((e.key==='p'||e.key==='P')&&GATE!=='title'){
    e.preventDefault();e.stopImmediatePropagation();
    gateTogglePause();return}
  if(GATE!=='playing'){e.preventDefault();e.stopImmediatePropagation();
    gateStart();return}
  gateGesture()},true);
if(GCV){GCV.addEventListener('pointerdown',e=>{
  if(GATE!=='playing'){e.preventDefault();e.stopImmediatePropagation();
    gateStart();return}
  gateGesture()},true)}
/* What the judge reads back. Every one of these is a fact about the
   running page: whether the template is getting frames at all, whether the
   briefing was skipped, and whether a gesture has happened - the last
   because a page that opened straight into play must not have made a sound
   yet, and "no sound" is otherwise indistinguishable from a broken stub. */
function gateFacts(){return {state:GATE,frames:GATE_RAN,skipped:GATE_SKIPPED,
  seen:gateSeen(),gesture:GATE_GESTURE}}
function gateWrap(text,limit){const out=[];let line='';
  for(const ch of text){line+=ch;
    if(line.length>=limit){out.push(line);line=''}}
  if(line)out.push(line);return out}
function drawGate(){if(!GCV||GATE==='playing')return;
  const c=GCV.getContext('2d'),W=GCV.width,H=GCV.height;
  c.save();
  c.fillStyle=GATE==='title'?'SURFACE_TOKEN':'#05070fcc';
  c.fillRect(0,0,W,H);
  c.fillStyle='#dfe7f5';c.textAlign='center';
  c.font='22px ui-monospace,monospace';
  c.fillText(GATE==='title'?GTITLE:'一時停止',W/2,H/2-54);
  c.font='13px ui-monospace,monospace';
  if(GATE==='title'){
    /* The briefing table: objective, controls, threat - the three things a
       player needs before the first frame, in that order. Falls back to the
       instruction line for a template with no briefing, so a missing entry
       costs the framing rather than the screen. */
    let y=H/2-30;
    if(GBRIEF&&GBRIEF.length===3){
      const LABEL=['目標','操作','敵'];
      GBRIEF.forEach((line,i)=>{
        c.textAlign='left';
        c.fillStyle='CYAN_TOKEN';c.font='12px ui-monospace,monospace';
        c.fillText(LABEL[i],W/2-190,y);
        c.fillStyle='#dfe7f5';c.font='13px ui-monospace,monospace';
        gateWrap(line,30).forEach((part,j)=>{c.fillText(part,W/2-140,y+j*18)});
        y+=gateWrap(line,30).length*18+10});
      c.textAlign='center'}
    else{gateWrap(GHOW,34).forEach((line,i)=>{c.fillText(line,W/2,H/2-18+i*20)})}}
  c.font='15px ui-monospace,monospace';
  c.fillText(GATE==='title'?'タップ / SPACE ではじめる':'タップ / SPACE でつづける',
    W/2,H-46);
  c.font='12px ui-monospace,monospace';
  c.fillStyle='#9fb0c8';
  c.fillText('P で一時停止  /  M で消音',W/2,H-24);
  c.textAlign='left';c.restore()}
const GATE_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return GATE_RAF(function tick(t){
    /* Closed: the template never gets the frame, and the loop stays alive
       so one press can hand it back. */
    if(GATE!=='playing'){drawGate();GATE_RAF(tick);return}
    fn(t);GATE_RAN++})};
"""

#: Drives a generated page in node: hold the gate shut, count frames, press
#: start, count again. Recording the listeners is the whole point - a stubbed
#: ``addEventListener`` that drops them would make every page look gated.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [];
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') keyHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
run(10);
const before = gateFrames(), stateBefore = gateState();
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(10);
console.log(JSON.stringify({
  stateBefore: stateBefore, framesBeforePress: before,
  stateAfter: gateState(), framesAfterPress: gateFrames(),
  handlers: keyHandlers.length,
  /* Read off the running page, not the source: a briefing constant that
     never reaches the gate would still be in the file. */
  brief: typeof gateBrief === 'function' ? gateBrief() : null,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the gate can be pressed in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: How long the gate itself is allowed to stand between a person and the
#: game, once they have made their one input. One frame: the press is
#: handled, the next frame belongs to the template.
INSTANT_FRAMES = 1

#: The inputs a first-time player might actually reach for. "Any key" has
#: to mean any key, so the judge tries the ones that are easy to get wrong:
#: the letter that is also a shortcut, the arrow that is also a control,
#: and the tap, which is the only input a phone has.
FIRST_INPUTS: tuple[tuple[str, str], ...] = (
    ("key", " "),
    ("key", "Enter"),
    ("key", "ArrowRight"),
    ("key", "x"),
    # P is the pause key once the game is running. On the title screen it
    # used to do nothing at all, which made "press any key" false for
    # exactly one key.
    ("key", "p"),
    ("tap", ""),
)

#: Runs a generated page from load, with whatever the browser remembers,
#: and delivers at most one input. The whole claim is about the first few
#: frames, so the probe counts them rather than trusting a state name.
START_PROBE = """
const startNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : startNothing),
  apply: () => startNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
let startClock = 0;
globalThis.performance = { now: () => startClock };
const startKeys = [], startPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') startKeys.push(fn) };
globalThis.Image = function(){ return startNothing };
const startStore = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in startStore ? startStore[k] : null),
  setItem: (k, v) => { startStore[k] = String(v) },
  removeItem: (k) => { delete startStore[k] } };
globalThis.location = { reload: () => {} };
function startElement(tag){
  const el = { tagName: tag, style: {}, children: [], attrs: {}, handlers: {},
    appendChild(c){ this.children.push(c); return c },
    setAttribute(k, v){ this.attrs[k] = v }, getAttribute(k){ return this.attrs[k] },
    addEventListener(name, fn){ (this.handlers[name] = this.handlers[name] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => startNothing, width: 720, height: 320 };
  return el }
const startBody = startElement('body');
globalThis.document = { readyState: 'complete', body: startBody,
  createElement: startElement, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: (type, fn) => { if (type === 'pointerdown') startPointers.push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => startNothing }) };
let startQueued = null;
globalThis.requestAnimationFrame = (fn) => { startQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function startRun(n){ for (let i = 0; i < n && startQueued; i++) {
  const fn = startQueued; startQueued = null; startClock += 50 / 3; fn(startClock) } }
/* What the page does when nobody touches it. A first visit must be sitting
   on its briefing here; a return visit must already be playing. */
startRun(WARMUP_INPUT);
const startUntouched = gateFacts();
let startPressed = null;
if (INPUT_KIND === 'key') {
  const ev = { key: INPUT_KEY, code: 'Probe',
    preventDefault(){}, stopImmediatePropagation(){} };
  startKeys.forEach(fn => fn(ev));
  startPressed = 'key';
} else if (INPUT_KIND === 'tap') {
  startPointers.forEach(fn => fn({ pointerType: 'touch', pointerId: 1,
    clientX: 360, clientY: 160, preventDefault(){}, stopImmediatePropagation(){} }));
  startPressed = 'tap';
}
const startAfterInput = gateFacts();
/* One frame is all the gate is allowed once the input has landed. */
const startFrames = [];
for (let i = 0; i < 4; i++) { startRun(1); startFrames.push(gateFacts().frames) }
console.log(JSON.stringify({
  untouched: startUntouched, afterInput: startAfterInput,
  pressed: startPressed, frames: startFrames,
  facts: gateFacts(), warmup: WARMUP_INPUT,
  running: startQueued !== null,
  stored: Object.keys(startStore),
}));
"""


def start_probe_source(
    script: str,
    *,
    stored: dict[str, object] | None = None,
    kind: str = "none",
    key: str = " ",
    warmup: int = 3,
) -> str:
    """The page from load, with one input at most."""

    import json as _json

    payload = {
        name: (value if isinstance(value, str) else _json.dumps(value, ensure_ascii=False))
        for name, value in (stored or {}).items()
    }
    return (
        START_PROBE.replace("STORED_INPUT", _json.dumps(payload, ensure_ascii=False))
        .replace("WARMUP_INPUT", str(int(warmup)))
        .replace("INPUT_KIND", _json.dumps(kind))
        .replace("INPUT_KEY", _json.dumps(key))
        .replace("SCRIPT_PLACEHOLDER", script)
    )


__all__ = [
    "BRIEFINGS",
    "FIRST_INPUTS",
    "GATE_PREAMBLE",
    "INSTANT_FRAMES",
    "PREAMBLE_NAMES",
    "PROBE",
    "START_PROBE",
    "probe_source",
    "start_probe_source",
]
