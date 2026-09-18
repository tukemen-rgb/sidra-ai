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

import re

from sidra_ai.creation.probekit import seed_store

import json

from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: What the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "gateState",
    "gateFrames",
    "gateBrief",
    "gateBriefTable",
    "gateSaid",
    "gateSaidLines",
    "gateSaidForget",
    "gateSaidTable",
    "gateSkipped",
    "gateSeen",
    "gateGesture",
    "gateFacts",
    "attractOn",
    "attractRewind",
    "attractFacts",
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
        "帯の中で合わせて得点、濃い中央なら会心で 2 点",
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
        # The one briefing whose number is not the same on every rung
        # (C-1625). It said 「3 周」 on easy, where the race is two laps -
        # the wrong objective, on the screen a player cannot get past
        # without reading it. Filled in from the same RACING_LAPS the page
        # bakes into LAPS, so the two cannot drift apart again.
        "コースに沿って LAPS_TOKEN 周を走り切り、タイムを残す",
        "← → でハンドルを切る",
        "路上の障害物とコース外。どちらも減速（リタイアは無い）",
    ),
    "marble": (
        "ゲートを抜けながらコースの終わりまで転がる",
        "← → で玉を左右に寄せる",
        "コースを塞ぐブロック。当たれば転倒",
    ),
    "platformer": (
        "足場を渡り、ゴールの旗まで灯りを運ぶ",
        "← → で走り、↑ / SPACE でジャンプ（長押しで高く）",
        "底なしの隙間。落ちても灯籠まで戻るだけ",
    ),
}


#: The same three lines for a start screen written in English (C-1957).
#:
#: These are the first thing a player reads, and until this item they were
#: Japanese whatever language the request was in - the page's frame followed
#: the request from C-1956, and the screen drawn on the canvas did not.
#:
#: Kept beside the Japanese they translate rather than in another module:
#: two tables in two files is the drift C-1848 keeps naming. The racing
#: line carries ``LAPS_TOKEN`` in both languages because the lap count is
#: the product's number, filled from ``RACING_LAPS`` after this table is
#: read - not something either table decides.
BRIEFINGS_EN: dict[str, tuple[str, str, str]] = {
    "fishing": (
        "Time it inside the band to score; the darker middle is a perfect, worth 2",
        "SPACE / tap to time it",
        "The band is narrow and the marker never rests",
    ),
    "catch": (
        "Catch everything that falls, in the tray",
        "← → / mouse to move the tray",
        "The falling never stops, and a drop does not come back",
    ),
    "adventure": (
        "Find the key and reach the chest",
        "Arrows / WASD to walk, SPACE to strike",
        "Enemies that wander, and rocks and grass in the way",
    ),
    "duel": (
        "Charge, fire, and take the opponent's health down first",
        "Hold SPACE to charge, release to fire, ↑ ↓ to dodge",
        "The opponent is a quick-draw or a charger (the screen says which)",
    ),
    "shooter": (
        "Shoot down every wave that comes",
        "← → to move, SPACE to keep firing",
        "The waves speed up. Three collisions end it",
    ),
    "puzzle": (
        "Clear blocks of one colour and tidy the board",
        "← ↑ → ↓ to move the cursor, SPACE to clear",
        "Fewer than two cannot be cleared. It ends when no move is left",
    ),
    "kaiju": (
        "Break a leg, hit the head that comes down. Three cycles to finish it",
        "← → to walk, SPACE to shoot",
        "The beast's blow, and the fissure that runs (the line is the warning)",
    ),
    "racing": (
        "Follow the course for LAPS_TOKEN laps and keep the time",
        "← → to steer",
        "Obstacles on the road and the ground off it. Both slow you (there is no retiring)",
    ),
    "marble": (
        "Roll to the end of the course, through the gates on the way",
        "← → to steer the marble",
        "Blocks across the course. Hit one and it topples",
    ),
    "platformer": (
        "Cross the platforms and carry the light to the flag",
        "← → to run, ↑ / SPACE to jump (hold it to go higher)",
        "Bottomless gaps. A fall only sends you back to the lantern",
    ),
}

#: Derived from the Japanese table, never counted by hand: a template added
#: with a briefing and no English raises at import instead of drawing three
#: Japanese lines onto an English start screen. The second check is the one
#: C-1945 learned - a line that is present but still Japanese is invisible
#: to a count that only asks whether the key exists.
_MISSING_BRIEF_EN = sorted(set(BRIEFINGS) - set(BRIEFINGS_EN))
_SHORT_BRIEF_EN = sorted(
    key for key, lines in BRIEFINGS_EN.items() if len(lines) != len(BRIEFINGS[key])
)
_UNTRANSLATED_BRIEF_EN = sorted(
    line
    for lines in BRIEFINGS_EN.values()
    for line in lines
    if re.search(r"[぀-ゟ゠-ヿ一-鿿]", line)
)
if _MISSING_BRIEF_EN or _SHORT_BRIEF_EN or _UNTRANSLATED_BRIEF_EN:  # pragma: no cover
    raise RuntimeError(
        f"startscreen.BRIEFINGS_EN has no English for {_MISSING_BRIEF_EN}, "
        f"the wrong number of lines for {_SHORT_BRIEF_EN}, and still carries "
        f"Japanese in {_UNTRANSLATED_BRIEF_EN}"
    )

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
/* WHICH briefing was read, not merely that one was (C-1738). The key is
   the template's name and the value used to be '1', which says "this
   template has been opened" - and the two are the same claim only while
   every game a template makes says the same three lines. Racing's 目標
   line does not: it carries the lap count, so 「コースに沿って 2 周を
   走り切り」 and 「4 周」 are different news under one mark, and the
   second game skipped a screen the player had never seen. (My own
   DEVICE_WIDE note in together.py said "the three lines belong to the
   template"; this is that note being wrong.) The fingerprint is of the
   words the screen actually prints, so a briefing that changes for any
   reason - a new lap count, a rewritten line - is news again exactly
   once. */
function gateBriefHash(){
  const text=(GBRIEF&&GBRIEF.length)?GBRIEF.join('\u0001'):String(GHOW||'');
  let h=2166136261;
  for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619)>>>0}
  return 'b'+h.toString(36)}
function gateSeen(){const s=gateStore();
  try{const raw=s&&s.getItem(GATE_SEEN_KEY);if(!raw)return false;
    if(raw===gateBriefHash())return true;
    /* '1' is what every page wrote before the words were recorded:
       somebody read the three lines they were shown, and showing them
       again is the thing C-1111 removed. Adopted, and re-stamped, so the
       NEXT change is news. */
    if(raw==='1'){gateRemember();return true}
    return false}catch(e){return false}}
function gateRemember(){const s=gateStore();
  try{if(s)s.setItem(GATE_SEEN_KEY,gateBriefHash())}catch(e){}}
/* The gesture the AudioContext has been waiting for. Kept apart from
   starting, because a page that opened straight into play (C-1111) has had
   no gesture yet - and a sound played without one is a sound the browser
   refuses and the player learns the game does not have. */
function gateGesture(){if(GATE_GESTURE)return;GATE_GESTURE=true;
  try{sfx('step')}catch(e){}}
/* --- the demo behind the title (§17, C-1414) -------------------------- */
/* Wired per template, because a demo is a template that plays itself and
   most of these do not: with no input the basket never moves and the hero
   never walks, so the "demo" would be a still picture with a veil over it.
   attract.ATTRACT_UNWIRED names every unwired one and why, one line each,
   and this token is what that table decides. */
const ATTRACT_WIRED=ATTRACT_WIRED_TOKEN;
/* ATTRACT_LIVE is the pilot's receipt (C-1338): a piloted demo exists to
   show the game's core verb, and the pilot line sets this the moment the
   verb lands (the shooter's, when something is shot down). A demo that
   held the trigger and hit nothing is a still worth doubting, and the
   judge reads this instead of guessing from motion. */
let ATTRACT_FRAMES=0,ATTRACT_LOOPS=0,ATTRACT_ASKED=false,ATTRACT_LIVE=0;
/* The demo slice (C-1438): a clock-bound template has no ending of its
   own - the round clock is its only break, and the clock does not run
   behind the title - so its demo rewinds every SLICE frames instead,
   the arcade's habit of showing fifteen seconds and starting over.
   Zero means the template ends itself and roundEnded() alone decides. */
const ATTRACT_SLICE=ATTRACT_SLICE_TOKEN;let ATTRACT_MARK=0;
function attractOn(){return ATTRACT_WIRED&&GATE==='title'}
/* The demo's leftovers, cleared before the game is handed over - and
   between demo goes. The template's own reset is the substituted call; the
   shared parts are cleared here because the demo drove those too. A trail
   nobody drove must not be banked as somebody's line (C-1401), and a
   demo's failures are not the player's (C-1122). */
function attractRewind(){if(!ATTRACT_WIRED)return;
  try{ATTRACT_RESET_TOKEN}catch(e){}
  try{ghostForget()}catch(e){}
  try{gateSaidForget()}catch(e){}
  try{failBeatsReset()}catch(e){}
  try{grazeReset()}catch(e){}
  try{comboMiss()}catch(e){}}
function attractFacts(){return {wired:ATTRACT_WIRED,frames:ATTRACT_FRAMES,
  loops:ATTRACT_LOOPS,live:ATTRACT_LIVE}}
function gateStart(){if(GATE==='playing')return;
  /* Whatever the demo did belongs to the demo (C-1414). Rewound before the
     state flips, so the first frame a player is given is the first frame of
     a go - not the middle of one they watched. */
  attractRewind();
  /* ...and the line about how to hold the phone has had its moment
     (C-1415): it belongs to the title screen, not to a running game. */
  try{rotateHide()}catch(e){}
  GATE='playing';gateRemember();gateGesture()}
function gateTogglePause(){if(GATE==='title')return;
  GATE=GATE==='paused'?'playing':'paused'}
/* --- what the page just said (§30 事実 1, C-1776) --------------------- */
/* say() writes one line over the last one and takes it away on a timer,
   so every word a template speaks is on a clock the player does not hold.
   §30 事実 1 asks for the opposite: text at the reader's pace. For most
   of these lines the clock costs nothing - the line repeats when the
   action does, and the standing facts (gems, key, charm, room) are on the
   HUD, which never expires. One line is neither. Adventure's stone names
   the knock order for THIS run - KORDER is shuffled per seed, so no
   briefing can carry it - and the stone stands in the forest while the
   marks it speaks of are in the cave. Crossing the rooms says the room's
   name, which overwrites the order before it can ever be used, and
   re-reading it is a walk back through the roamers. That is a line whose
   reading speed costs hearts.
   So the recent lines are kept and the pause screen shows them: pause is
   already the one place that answers "what was the key again?" (C-1442),
   and it is the screen a player reaches for when they need a moment.
   Three, and three stored - the drawer shows every line it holds, because
   a log with hidden entries is a log that lies about what it kept. Three
   is what the walk from the stone to the marks needs: the room's name and
   one hit, with the stone still first. Repeats collapse, so a second
   「いたい。」 cannot push the stone out. Nothing else is filtered: the
   page decides what it says, and a log that guesses which lines mattered
   is a log that drops the one that did. */
const GSAID_KEEP=3;let GSAID=[];
function gateSaid(t){const line=String(t==null?'':t);if(!line)return;
  if(GSAID[GSAID.length-1]===line)return;
  GSAID.push(line);while(GSAID.length>GSAID_KEEP)GSAID.shift()}
function gateSaidLines(){return GSAID.slice()}
function gateSaidForget(){GSAID=[]}
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
  seen:gateSeen(),gesture:GATE_GESTURE,brief:gateBriefHash()}}
function gateWrap(text,limit){const out=[];let line='';
  for(const ch of text){line+=ch;
    if(line.length>=limit){out.push(line);line=''}}
  if(line)out.push(line);return out}
/* The briefing table: objective, controls, threat - the three things a
   player needs before the first frame, in that order. Falls back to the
   instruction line for a template with no briefing, so a missing entry
   costs the framing rather than the screen.
   Drawn on the PAUSE screen as well as the title (C-1442... C-1444): the
   briefing is skipped from the second visit onward by design - it is only
   news once - and pause was the one place left that could answer "what
   was the key again?". Nothing new is written there; it is the same three
   lines, from the same function, so the two screens cannot drift apart. */
function gateBriefTable(c,W,H){
  let y=H/2-30;
  if(GBRIEF&&GBRIEF.length===3){
    const LABEL=['目標','操作','敵'];
    GBRIEF.forEach((line,i)=>{
      c.textAlign='left';
      c.fillStyle='CYAN_TOKEN';c.font=hudPx(13)+'px ui-monospace,monospace';
      c.fillText(LABEL[i],W/2-190,y);
      c.fillStyle='INK_TOKEN';c.font=hudPx(13)+'px ui-monospace,monospace';
      gateWrap(line,30).forEach((part,j)=>{c.fillText(part,W/2-140,y+j*18)});
      y+=gateWrap(line,30).length*18+10});
    c.textAlign='center'}
  else{gateWrap(GHOW,34).forEach((line,i)=>{c.fillText(line,W/2,H/2-18+i*20)});
    y=H/2-18+gateWrap(GHOW,34).length*20}
  /* Where the briefing stopped, so whatever comes next starts below it
     instead of at a literal somebody has to keep in step with it. */
  return y}
/* The lines the page said lately, on the pause screen only (§30 事実 1,
   C-1776). Not on the title: nothing has been said yet, and a heading
   over an empty drawer is worse than no drawer. Laid out in the
   briefing's own two columns from the y the briefing itself ended at, so
   the two blocks cannot overlap whatever the briefing wraps to, and the
   walk stops before the 「つづける」 line rather than writing over it -
   the way out must never be the thing that gets covered. */
function gateSaidTable(c,W,H,y){
  const said=gateSaidLines();if(!said.length)return y;
  c.textAlign='left';
  c.fillStyle='CYAN_TOKEN';c.font=hudPx(13)+'px ui-monospace,monospace';
  c.fillText('直前',W/2-190,y);
  c.fillStyle='INK_TOKEN';c.font=hudPx(13)+'px ui-monospace,monospace';
  said.forEach(line=>{
    gateWrap(line,30).forEach(part=>{
      if(y<=H-64){c.fillText(part,W/2-140,y);y+=16}})});
  c.textAlign='center';return y}
function drawGate(){if(!GCV||GATE==='playing')return;
  const c=GCV.getContext('2d'),W=GCV.width,H=GCV.height;
  c.save();
  /* A demo running underneath is worth seeing, so the title veils it
     rather than covering it (C-1414). With no demo there is nothing under
     the panel and the opaque field is the more readable one. */
  c.fillStyle=(GATE==='title'&&!ATTRACT_FRAMES)?'SURFACE_TOKEN':'SCRIM_TOKEN'+'cc';
  c.fillRect(0,0,W,H);
  c.fillStyle='INK_TOKEN';c.textAlign='center';
  c.font=hudPx(22)+'px ui-monospace,monospace';
  c.fillText(GATE==='title'?GTITLE:'一時停止',W/2,H/2-54);
  c.font=hudPx(13)+'px ui-monospace,monospace';
  const briefEnd=gateBriefTable(c,W,H);
  if(GATE==='paused')gateSaidTable(c,W,H,briefEnd);
  c.font=hudPx(15)+'px ui-monospace,monospace';
  c.fillText(GATE==='title'?'タップ / SPACE ではじめる':'タップ / SPACE でつづける',
    W/2,H-46);
  c.font=hudPx(13)+'px ui-monospace,monospace';
  c.fillStyle='#9fb0c8';
  c.fillText('P で一時停止  /  M で消音',W/2,H-24);
  c.textAlign='left';c.restore()}
const GATE_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  /* Recorded on the way in: during a demo frame this is how the gate knows
     the template asked for the next one itself. */
  ATTRACT_ASKED=true;
  return GATE_RAF(function tick(t){
    /* Closed: the template never gets the frame, and the loop stays alive
       so one press can hand it back. */
    if(GATE!=='playing'){
      /* ...except behind the title of a wired template, where the frame
         *is* the demo (§17). The game runs and the veil goes over it.
         Nothing it does is banked: the round clock does not start until
         play does, and roundBank refuses to open behind the title at all
         (the untouched guard alone was not enough - it comes after the
         score has been read into ROUND_FINAL). The
         loop is normally re-armed by the demo's own step() asking for its
         next frame, which is why this branch does not arm it as well -
         two arms per frame doubles the loop every frame. ATTRACT_ASKED is
         the check: a template that asks for nothing still gets its title
         redrawn rather than freezing the gate. */
      if(attractOn()){ATTRACT_ASKED=false;ATTRACT_FRAMES++;
        /* The demo's hand on the template's own controls (C-1338): one
           substituted line per template, the arcade's recorded input in
           its smallest form. It drives the same state a player would, so
           the template's reset is all the handover needs to let go. */
        try{ATTRACT_PILOT_TOKEN}catch(e){}
        fn(t);
        /* The demo reached its own ending: another go, so the title is
           never a frozen goal screen. */
        try{if(roundEnded()||(ATTRACT_SLICE>0&&ATTRACT_FRAMES-ATTRACT_MARK>=ATTRACT_SLICE)){
          ATTRACT_LOOPS++;ATTRACT_MARK=ATTRACT_FRAMES;attractRewind()}}catch(e){}
        drawGate();if(!ATTRACT_ASKED){GATE_RAF(tick)}return}
      drawGate();GATE_RAF(tick);return}
    fn(t);GATE_RAN++})};
"""

#: Drives a generated page in node: hold the gate shut, count frames, press
#: start, count again. Recording the listeners is the whole point - a stubbed
#: ``addEventListener`` that drops them would make every page look gated.
PROBE = KEY_EVENT_JS + """
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
const press = probeKey(' ');
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


#: A page started, paused and resumed, reporting what was drawn each time.
#:
#: Every name here carries a ``pg`` prefix: the templates declare ``keys``,
#: ``ctx`` and ``store`` of their own at the top level, and a harness that
#: reuses one of those does not shadow it - the page refuses to parse at
#: all (C-1436 was the same lesson from inside a loop).
PAUSE_PROBE = KEY_EVENT_JS + """
const pgNothing = new Proxy(function(){}, {
  get: (t,k)=>(k===Symbol.toPrimitive?()=>0:pgNothing), apply:()=>pgNothing, set:()=>true });
globalThis.matchMedia = () => ({ matches: false });
let pgClock = 0; globalThis.performance = { now: () => pgClock };
const pgKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') pgKeys.push(fn) };
globalThis.Image = function(){ return pgNothing };
const pgStore = STORE_INPUT;
globalThis.localStorage = { getItem:k=>k in pgStore?pgStore[k]:null,
  setItem:(k,v)=>{pgStore[k]=String(v)}, removeItem:k=>{delete pgStore[k]} };
let pgDrawn = [];
const pgCtx = new Proxy({ fillText: (t)=>{ pgDrawn.push(String(t)) } },
  { get:(t,k)=>(k in t?t[k]:(k===Symbol.toPrimitive?()=>0:pgNothing)), set:()=>true });
globalThis.document = { readyState:'complete', body:{children:[]},
  createElement:()=>pgNothing, querySelector:()=>null,
  getElementById:()=>({ width:720, height:320, style:{}, addEventListener:()=>{},
    getBoundingClientRect:()=>({left:0,top:0,width:720,height:320}), getContext:()=>pgCtx }) };
globalThis.location = { reload: () => {} };
let pgQueued = null;
globalThis.requestAnimationFrame = (fn) => { pgQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function pgKey(k){ const e = probeKey(k);
  pgKeys.forEach(fn=>fn(e)) }
function pgStep(n){ for(let i=0;i<n && pgQueued;i++){
  const fn=pgQueued; pgQueued=null; pgClock+=16; fn(pgClock) } }
/* Whatever the gate is showing before anything is pressed. On a first
   visit this is the title; on a return visit the briefing is skipped by
   design and the game is already running. */
const atLoad = (function(){ pgDrawn=[]; pgStep(3); return pgDrawn.slice() })();
pgKey(' '); pgStep(8);
const playing = (function(){ pgDrawn=[]; pgStep(3); return pgDrawn.slice() })();
pgKey('p'); pgStep(3);
const paused = (function(){ pgDrawn=[]; pgStep(3); return pgDrawn.slice() })();
pgKey('p'); pgStep(3);
const resumed = (function(){ pgDrawn=[]; pgStep(3); return pgDrawn.slice() })();
console.log(JSON.stringify({
  gate: gateState(), brief: (function(){ try { return gateBrief() } catch(e){ return null } })(),
  skipped: (function(){ try { return gateSkipped() } catch(e){ return null } })(),
  atLoad: atLoad, playing: playing, paused: paused, resumed: resumed,
}));
"""


def pause_probe_source(script: str, *, store: dict[str, str] | None = None) -> str:
    """The page driven to a pause and back, with ``store`` behind it."""

    return PAUSE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "STORE_INPUT", json.dumps(store or {}, ensure_ascii=False)
    )


#: A line the page said, read back after its own timer took it away
#: (§30 事実 1, C-1776).
#:
#: The whole claim is about a message that is GONE: the probe drives the
#: page's own ``say()`` with the page's own literal, runs frames until
#: ``msgT`` reaches zero, checks the words are really off the playing
#: screen, and only then presses P. So "readable on pause" cannot be
#: satisfied by the message simply still being up.
#:
#: ``rr`` prefixes throughout, for PAUSE_PROBE's reason: a name the
#: templates already use at the top level does not shadow here, it stops
#: the page parsing.
REREAD_PROBE = KEY_EVENT_JS + """
const rrNothing = new Proxy(function(){}, {
  get: (t,k)=>(k===Symbol.toPrimitive?()=>0:rrNothing), apply:()=>rrNothing, set:()=>true });
globalThis.matchMedia = () => ({ matches: false });
let rrClock = 0; globalThis.performance = { now: () => rrClock };
const rrKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') rrKeys.push(fn) };
globalThis.Image = function(){ return rrNothing };
const rrStore = {};
globalThis.localStorage = { getItem:k=>k in rrStore?rrStore[k]:null,
  setItem:(k,v)=>{rrStore[k]=String(v)}, removeItem:k=>{delete rrStore[k]} };
let rrDrawn = [], rrAt = [];
/* Where, as well as what: the drawer's promise is partly a layout one -
   it must start below the briefing and stop above the way out - and a
   list of strings cannot say whether two blocks were written over each
   other. */
const rrCtx = new Proxy({ fillText: (t,x,y)=>{ rrDrawn.push(String(t));
    rrAt.push([String(t), x, y]) } },
  { get:(t,k)=>(k in t?t[k]:(k===Symbol.toPrimitive?()=>0:rrNothing)), set:()=>true });
globalThis.document = { readyState:'complete', body:{children:[]},
  createElement:()=>rrNothing, querySelector:()=>null,
  getElementById:()=>({ width:720, height:320, style:{}, addEventListener:()=>{},
    getBoundingClientRect:()=>({left:0,top:0,width:720,height:320}), getContext:()=>rrCtx }) };
globalThis.location = { reload: () => {} };
let rrQueued = null;
globalThis.requestAnimationFrame = (fn) => { rrQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* A press, dispatched the way the DOM dispatches one. The shared
   probeKey stubs stopImmediatePropagation as a no-op on purpose - a probe
   that omitted it would throw - and every other probe hands the same event
   to every listener regardless. Here that would measure the harness
   instead of the page: the gate's capture listener swallows the first
   press, so a template that ALSO sees it does something no player can
   make it do (the space that opens adventure's title also swung the sword
   and cut the grass, which put a line in the drawer the demo never said).
   The stub is left alone - it is shared - and the dispatch rule is honoured
   here, where the claim depends on it. */
function rrKey(k){ const e = probeKey(k); let rrStop = false;
  const rrSip = e.stopImmediatePropagation;
  e.stopImmediatePropagation = function(){ rrStop = true;
    if (rrSip) rrSip.call(e) };
  for (const fn of rrKeys) { fn(e); if (rrStop) break } }
function rrStep(n){ for(let i=0;i<n && rrQueued;i++){
  const fn=rrQueued; rrQueued=null; rrClock+=16; fn(rrClock) } }
function rrFrame(n){ rrDrawn=[]; rrAt=[]; rrStep(n===undefined?3:n);
  return rrDrawn.slice() }
/* The y of every row whose text is one of `want`, from the last frame. */
function rrRows(want){ return rrAt.filter(r=>want.indexOf(r[0])>=0).map(r=>r[2]) }
const rrSays = typeof say === 'function';
const rrOut = { says: rrSays };
if (rrSays) {
  /* The demo behind the title, given time to speak (§17). Without these
     frames the attract loop never runs and "the demo's words are not the
     player's" is a claim about nothing. */
  rrStep(240);
  rrOut.demoSaid = gateSaidLines().length;
  /* Past the title, so the gate is 'playing' and the template is running. */
  rrKey(' '); rrStep(8);
  /* A demo's words are the demo's: whatever the attract loop said behind
     the title must not be waiting on the player's pause screen. */
  rrOut.forgotDemo = gateSaidLines().length === 0;
  const rrLine = LINE_PLACEHOLDER;
  say(rrLine);
  rrOut.upWhileTiming = rrFrame().indexOf(rrLine) >= 0;
  /* Run the message's own timer out. The page decides how long that is. */
  let rrGuard = 0;
  while (msgT > 0 && rrGuard++ < 6000) { rrStep(1) }
  rrOut.expired = msgT <= 0;
  rrOut.upAfterExpiry = rrFrame().indexOf(rrLine) >= 0;
  /* Only now is there anything to read back. */
  rrKey('p'); rrStep(3);
  const rrPaused = rrFrame();
  rrOut.gate = gateState();
  rrOut.onPause = rrPaused.indexOf(rrLine) >= 0;
  rrOut.pauseHeading = rrPaused.indexOf('一時停止') >= 0;
  rrOut.drawnOnPause = gateSaidLines().filter(l => rrPaused.indexOf(l) >= 0).length;
  rrOut.kept = gateSaidLines().length;
  /* Back to play: the drawer belongs to the paused screen. */
  rrKey('p'); rrStep(3);
  rrOut.onResumed = rrFrame().indexOf(rrLine) >= 0;
  /* The cap is real, and it is the oldest that goes. */
  const rrExtra = [];
  for (let i = 0; i < GSAID_KEEP + 1; i++) { rrExtra.push('probe-line-' + i); say(rrExtra[i]) }
  const rrHeld = gateSaidLines();
  rrOut.capHolds = rrHeld.length === GSAID_KEEP;
  rrOut.oldestDropped = rrHeld.indexOf(rrExtra[0]) < 0;
  rrOut.newestHeld = rrHeld.indexOf(rrExtra[rrExtra.length - 1]) >= 0;
  /* A line repeated is one line: a run of the same words must not push
     out the line that mattered. */
  gateSaidForget(); say('probe-same'); say('probe-same'); say('probe-same');
  rrOut.repeatsCollapse = gateSaidLines().length === 1;
  rrOut.keep = GSAID_KEEP;
  /* A full drawer, in the page's own longest words, drawn on the page's
     own canvas: the drawer's promise is that it shows every line it
     holds, and the only thing that can break that is the room between
     the briefing and the way out. Counted as whole lines - every part a
     wrap produces has to be on the screen, or the line is cut, not shown. */
  gateSaidForget();
  LINES_PLACEHOLDER.forEach(l => say(l));
  rrKey('p'); rrStep(3);
  /* One frame, so a row count is a row count and not three of them. */
  const rrFull = rrFrame(1);
  rrOut.fullKept = gateSaidLines().length;
  rrOut.fullShown = gateSaidLines().filter(l =>
    gateWrap(l, 30).every(part => rrFull.indexOf(part) >= 0)).length;
  /* ...and where it sits. A full drawer must start below the briefing
     and stop above the way out; both blocks are on one 320px canvas, so
     this is the measurement that says the drawer did not write over the
     three lines pause exists to show or over 「つづける」 itself. */
  const rrSaidRows = rrRows(gateSaidLines().reduce(
    (all,l)=>all.concat(gateWrap(l,30)), ['直前']));
  const rrBriefRows = rrRows((GBRIEF||[]).reduce(
    (all,l)=>all.concat(gateWrap(l,30)), ['目標','操作','敵']));
  rrOut.exitShown = rrFull.indexOf('タップ / SPACE でつづける') >= 0;
  rrOut.drawerRows = rrSaidRows.length;
  rrOut.belowBrief = rrBriefRows.length > 0 && rrSaidRows.length > 0
    && Math.min.apply(null, rrSaidRows) > Math.max.apply(null, rrBriefRows);
  rrOut.aboveExit = rrSaidRows.length > 0
    && Math.max.apply(null, rrSaidRows) <= 320 - 64;
  /* Longer than any line these pages say today, which is the point: the
     drawer's stop is a guard, and a guard nothing reaches is a guard
     nobody has checked. Three of these wrap to more rows than the band
     between the briefing and 「つづける」 has room for, so the walk must
     cut them - and every row it did draw must still be above the way out.
     The words are the probe's, never the page's: a page literal long
     enough to do this does not exist. */
  gateSaidForget();
  const rrLong = ['長い行の一', '長い行の二', '長い行の三'].map(
    (tag,i)=>tag + '。' + 'あいうえおかきくけこ'.repeat(9));
  rrLong.forEach(l => say(l));
  const rrLongFrame = rrFrame(1);
  const rrWanted = gateSaidLines().reduce((n,l)=>n + gateWrap(l,30).length, 0);
  const rrLongRows = rrRows(gateSaidLines().reduce(
    (all,l)=>all.concat(gateWrap(l,30)), []));
  rrOut.longWanted = rrWanted;
  rrOut.longDrawn = rrLongRows.length;
  rrOut.longClipped = rrLongRows.length < rrWanted;
  rrOut.longAboveExit = rrLongRows.length > 0
    && Math.max.apply(null, rrLongRows) <= 320 - 64;
  rrOut.longExitShown = rrLongFrame.indexOf('タップ / SPACE でつづける') >= 0;
}
console.log(JSON.stringify(rrOut));
"""


def reread_probe_source(
    script: str, *, line: str, lines: tuple[str, ...] = ()
) -> str:
    """The page driven so one of its own said lines expires, then paused.

    ``line`` is the one whose timer is run out and read back; ``lines``
    fills the drawer, to see whether a full one is drawn whole.
    """

    return (
        REREAD_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("LINE_PLACEHOLDER", json.dumps(line, ensure_ascii=False))
        .replace("LINES_PLACEHOLDER", json.dumps(list(lines), ensure_ascii=False))
    )


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

    payload = seed_store(stored)
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
    "PAUSE_PROBE",
    "PROBE",
    "START_PROBE",
    "pause_probe_source",
    "REREAD_PROBE",
    "reread_probe_source",
    "probe_source",
    "start_probe_source",
]
