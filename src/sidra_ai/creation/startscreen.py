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
PREAMBLE_NAMES: tuple[str, ...] = ("gateState", "gateFrames", "gateBrief")

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
}

GATE_PREAMBLE = """
/* --- start screen and pause (installed first: its overlay draws last) --- */
const GCV=document.getElementById('stage');
const GTITLE=TITLE_TOKEN,GHOW=HOWTO_TOKEN,GBRIEF=BRIEF_TOKEN;
let GATE='title',GATE_RAN=0;
function gateState(){return GATE}
function gateFrames(){return GATE_RAN}
function gateBrief(){return GBRIEF}
function gateStart(){if(GATE==='playing')return;
  /* The press that starts the game is the user gesture the AudioContext has
     been waiting for; a game whose first sound is silent taught the player
     it has none. */
  GATE='playing';try{sfx('step')}catch(e){}}
function gateTogglePause(){if(GATE==='title')return;
  GATE=GATE==='paused'?'playing':'paused'}
addEventListener('keydown',e=>{
  if(e.key==='p'||e.key==='P'){e.preventDefault();e.stopImmediatePropagation();
    gateTogglePause();return}
  if(GATE!=='playing'){e.preventDefault();e.stopImmediatePropagation();
    gateStart()}},true);
if(GCV){GCV.addEventListener('pointerdown',e=>{
  if(GATE!=='playing'){e.preventDefault();e.stopImmediatePropagation();
    gateStart()}},true)}
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


__all__ = ["BRIEFINGS", "GATE_PREAMBLE", "PREAMBLE_NAMES", "PROBE", "probe_source"]
