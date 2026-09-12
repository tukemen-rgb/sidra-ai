"""A round that is guaranteed to end, so the game can be put down.

§8 事実 1 of the play notes: the sessions people finish are the ones that
reach a break. A generated page that runs forever is not "endless content",
it is a page with no moment to stop at - and every one of the templates
here can be left running, so "how long is a go?" had no answer at all for
two of them and no *bound* for the rest.

The mechanism is one shared clock, not nine timers:

* It counts **played** time, from the timestamp the browser hands the loop.
  The start screen and the pause both hold the frame back before this
  wrapper is reached, so a game sitting on its title screen or paused burns
  none of its sixty seconds.
* It defers to the template. Seven of the nine already end on their own -
  ``state`` leaves its live value and their own screen takes over. The
  clock watches for that and never fires; ``ROUND_LIVE`` is the one thing
  it has to be told, and the metric checks that table against the script.
* When it does fire, it holds the loop the way ``hitstop`` does - the frame
  that was on screen stays there, under a banner - rather than stopping it.
  A loop that was dropped could not be handed back.

Coming back is deliberately two different things. A template with its own
end state has its own restart already (``R``), and its own handler still
runs while the banner is up: the clock sees ``state`` go live again and
gets out of the way. A template with no end state at all (fishing, catch)
has nothing to go back to, so ``R`` re-runs the page - which, since
C-1113, is also how a tuning change is applied.
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from sidra_ai.creation.juice import HAPTIC_ROUND
from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: The bound itself. Sixty seconds is §8's number, not a guess of ours.
ROUND_SECONDS = 60

#: The state each template calls "still playing". Written down rather than
#: derived because the opposite - a list of end states - would silently stop
#: covering a template that grew a new way to lose. Empty means the template
#: has no state machine at all and therefore never ends by itself; those are
#: exactly the two the clock exists for.
ROUND_LIVE: dict[str, tuple[str, ...]] = {
    "adventure": ("play",),
    "catch": (),
    "duel": ("play",),
    "fishing": (),
    "kaiju": ("wake", "fight"),
    "marble": ("roll",),
    "platformer": ("play",),
    "puzzle": ("play",),
    "racing": ("race",),
    "shooter": ("play",),
}

#: What each template counts, as an expression its own page can evaluate,
#: and what to call it on screen. Higher is always better: a mixed
#: convention would make "あと n" mean two different things.
#:
#: Written down per template because there is no shared score variable and
#: inventing one would mean rewriting nine games. The judge evaluates these
#: on the running page, so an expression that stopped being true would be
#: caught rather than silently reporting nothing.
ROUND_SCORE: dict[str, tuple[str, str]] = {
    "adventure": ("hero.gems", "宝石"),
    # Points rather than catches since C-1405: the multiplier is in it.
    "catch": ("score", "得点"),
    # Damage dealt, not health kept: a duel lost 3-2 was closer than one
    # lost 3-0, and only the first of those is worth chasing.
    "duel": ("3-e.hp", "与ダメージ"),
    # Points rather than fish since C-1331: the 会心 double is in it. The
    # fish count stays on the HUD beside it, per C-1405's precedent.
    "fishing": ("score", "得点"),
    # Head hits plus what the graze runs paid (C-1419), the same shape
    # the shooter took under C-1406: an expression rather than a rename,
    # so 周期 stays the count it always was on the HUD.
    "kaiju": ("cycles+grazeFacts().paid", "得点"),
    "marble": ("score", "スコア"),
    "platformer": ("me.gems", "宝石"),
    "puzzle": ("score", "得点"),
    "racing": ("times.length", "完了ラップ"),
    # Kills plus what the graze runs paid (C-1406). An expression
    # rather than a rename, so 撃墜 stays the count it always was.
    "shooter": ("score+grazeFacts().paid", "得点"),
}

#: The second key, for the four templates whose score has a ceiling.
#:
#: C-1124: a race is scored by laps completed and there are three of them,
#: so the first finish sets a best that no later run can beat - the strip
#: says 自己ベスト更新 once and then nothing it offers is reachable again.
#: The same shape in three others: damage dealt out of three, cycles out of
#: three, gems out of however many the room holds. Each gets a tiebreak the
#: player can still improve, compared only when the scores are level.
#:
#: ``better`` is 'more' or 'less'. The expression is evaluated on the page,
#: like ``ROUND_SCORE``, so a renamed variable fails the judge rather than
#: silently disabling the tiebreak.
ROUND_TIE: dict[str, tuple[str, str, str]] = {
    # The briefing promises lap times; this is what makes that true.
    "racing": ("times.reduce((a,b)=>a+b,0)", "less", "合計タイム"),
    # What was left of you when it ended. Winning 3-0 beats winning 3-2.
    "duel": ("p.hp", "more", "残り体力"),
    "kaiju": ("me.hp", "more", "残り体力"),
    "adventure": ("hero.hp", "more", "残り体力"),
}


#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``roundFacts`` would
#: break only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "roundLive",
    "roundEnded",
    "roundLost",
    "roundTouched",
    "roundTieBeats",
    "roundTieFacts",
    "roundFacts",
    "roundAskReady",
    "roundScore",
    "roundBest",
    "ROUND_DONE",
    "ROUND_LIMIT_MS",
    "roundRemainMs",
    "roundLeft",
    "roundClockDue",
    "roundClockFacts",
    "roundTickFacts",
)

#: Every ``state='...'`` a template assigns. Read by the judge, so the live
#: table above cannot drift away from the page it describes.
_STATE_ASSIGN = re.compile(r"""state\s*=\s*['"]([A-Za-z]+)['"]""")


def states_in(script: str) -> set[str]:
    """Every value this template ever puts in ``state``."""

    return set(_STATE_ASSIGN.findall(script))


def live_gaps(template: str, script: str) -> list[str]:
    """Where the live-state table and the template disagree.

    A live state the script never assigns is a typo that would make the
    clock fire over a game that had not finished; a template with states
    but no live entry would have its own ending ignored.
    """

    declared = set(ROUND_LIVE.get(template, ()))
    assigned = states_in(script)
    gaps = [f"{name}: never assigned by the template" for name in sorted(declared - assigned)]
    if assigned and not declared:
        gaps.append(f"has states {sorted(assigned)} but no live state declared")
    if declared and not assigned:
        gaps.append("declares live states the template does not have")
    return gaps


ROUND_PREAMBLE = """
/* --- the round clock: every go reaches a break (§8 事実 1) ------------- */
const ROUND_LIVE=ROUND_LIVE_TOKEN,ROUND_LIMIT_MS=ROUND_LIMIT_TOKEN;
const RCV=document.getElementById('stage');
let ROUND_DONE=false,ROUND_T0=null,ROUND_MS=0,ROUND_REASON='';
/* The last frame's timestamp, and how long an absence has to be before the
   clock stops charging for it (C-1450). */
let ROUND_LAST=null;
const ROUND_GAP_MS=ROUND_GAP_TOKEN;
/* The template's own verdict, when it has one. Guarded because two
   templates have no state machine at all - for them the clock is the only
   ending there is. */
function roundLive(){
  if(!ROUND_LIVE.length)return true;
  if(typeof state==='undefined')return true;
  return ROUND_LIVE.indexOf(state)>=0}
function roundEnded(){return ROUND_LIVE.length>0&&!roundLive()}
/* Lost, as opposed to simply over. A template with no losing state cannot
   lose: its round ends on the clock every single time, so treating that as
   a defeat would make the signal meaningless. */
/* Did the player do anything this round? (C-1123)
   A page left alone still plays: the race finishes, the basket catches
   what falls into it, and the monster never swings. Banking a personal
   best for that is the product congratulating somebody for walking away -
   and C-1110 will then offer them a line to paste about it. So an
   untouched round earns nothing: no best, no total toward a colour, no
   ghost, no streak. It still *plays*, and it still ends properly; what it
   does not do is claim the result was theirs.

   Only input during play counts. The press that dismisses the briefing is
   how you get to the game, not playing it. */
let ROUND_TOUCHED=false,ROUND_PLAYED_A_FRAME=false;
function roundTouched(){return ROUND_TOUCHED}
/* Gated on a frame having been drawn in play, not on the gate's state at
   the moment of the event: the gate's own listener is registered first and
   flips the state inside the very keypress that opened it, so a listener
   asking 「are we playing?」 sees 「yes」 for the press that asked to start.
   A frame is unambiguous - the starting press happens before any. */
function roundNote(){if(ROUND_PLAYED_A_FRAME){ROUND_TOUCHED=true}}
addEventListener('keydown',roundNote);
addEventListener('pointerdown',roundNote);
if(RCV){RCV.addEventListener('pointerdown',roundNote);
  RCV.addEventListener('pointermove',roundNote)}
function roundLost(){
  if(!ROUND_LIVE.length)return false;
  try{return failBeats()>0}catch(e){return false}}
function roundTick(t){
  /* The demo behind the title (C-1414) is the first thing that has ever
     reached this function before play. The go has not started, so the
     clock does not run: T0 re-anchors to the first playing frame, and a
     title left alone for a minute cannot ring the buzzer over its own
     demo. Guarded on 'title' alone - a paused game has started, and its
     frames do not reach here at all. */
  try{if(gateState()==='title'){ROUND_T0=null;return}}catch(e){}
  const now=(typeof t==='number'&&isFinite(t))?t:ROUND_MS+16;
  /* Time nobody could play is not time spent (C-1450). requestAnimationFrame
     stops while the tab is hidden, so the first frame back carries the whole
     absence in one step - and this clock read the raw difference, which meant
     a minute spent in another tab arrived as a minute of the round, buzzer
     and failure beat included, for a go the player never got to touch.
     The neighbour already does this: music.py re-anchors its scheduler with
     `if(MUSIC_NEXT<0||now-MUSIC_NEXT>1){MUSIC_NEXT=now}` when it wakes to
     find the world moved on. Same one second, for the same reason.
     The threshold has to be far above any real hitch and far below anything
     a player would call a pause: 1000ms is 60 frames at 60fps, so no stutter,
     no long paint, and no hitstop reaches it (hitstop withholds the DRAWING
     for a few frames - the loop keeps running at frame pace, measured, so
     nothing here forgives it and nothing needs to).
     Only the gap is forgiven, by pushing the start forward exactly as far as
     the page was away: everything before and after it is still charged. */
  if(ROUND_LAST!==null&&ROUND_T0!==null&&now-ROUND_LAST>ROUND_GAP_MS){
    ROUND_T0+=now-ROUND_LAST}
  ROUND_LAST=now;
  if(ROUND_T0===null){ROUND_T0=now}
  ROUND_MS=now-ROUND_T0;
  try{if(gateState()==='playing'){ROUND_PLAYED_A_FRAME=true}}catch(e){}
  /* The template finished on its own: its screen is the break, and the
     clock has nothing to add. Reset so a restart gets a full go. */
  if(roundEnded()){ROUND_T0=now;ROUND_MS=0;ROUND_REASON='template';return}
  /* A template that restarts in place (kaiju's tap, the duel's R) begins a
     round the bank has already been closed for. Without this the second
     go's strip - and the line C-1110 copies - would still be reporting the
     first one's score. */
  if(ROUND_BANKED&&!ROUND_DONE){ROUND_BANKED=false;ROUND_FINAL=null;ROUND_RECORD=false;
    /* ...and the round's own failure count with it (C-1122). Without this
       the next go inherits the last one's defeat. */
    try{failBeatsReset()}catch(e){}
    /* ...and whether anybody played it (C-1123). The keypress that asked
       for this round is not playing it. */
    ROUND_TOUCHED=false;ROUND_PLAYED_A_FRAME=false}
  /* Once the clock has fired, only an explicit restart clears it. An
     earlier version cleared it as soon as the template looked "live"
     again - but the clock fires precisely when the template has *not*
     finished, so ``state`` was still live and the banner lasted a single
     frame. Found by driving the page rather than by reading it. */
  if(ROUND_DONE){return}
  /* Before the buzzer's own branch, so the last tick and the buzzer are
     never the same frame (C-1448). */
  roundTickSound();
  if(ROUND_MS>=ROUND_LIMIT_MS){ROUND_DONE=true;ROUND_REASON='time';
    /* Running out of time without finishing fires the shared failure beat
       (C-1105), on every template - the branch is only reached when the
       round had *not* ended by itself, and nothing here asks which
       template it is. The old comment beside this line said the beat was
       "the only failure the four templates with no losing state have",
       which is not what the code does and not a count any table here
       supports: two templates have no ending of their own (catch and
       fishing, the empty entries in ROUND_LIVE) and five have no losing
       state (recap.LOSS_UNWIRED).
       **Whether this should stay is an open question, not a settled
       one.** 批評 #10 says a puzzle still being solved at 60 seconds has
       not failed, and §8 事実 1 is about session pacing - a break inside
       about a minute - rather than about declaring a loss. Changing it
       would also redefine creation_fail_beat, whose probe deliberately
       runs every template at its slowest pace so that the clock is what
       ends the go; its 10 is measuring exactly this beat. Recorded in
       BACKLOG E 節 (C-1127) for the owner rather than decided here. */
    try{failBeat(RCV?RCV.width/2:0,RCV?RCV.height/2:0)}catch(e){}}}
/* --- 終盤だけの残り時間 (§8 事実 1, C-1417) --------------------------- */
const ROUND_SHOW_MS=ROUND_SHOW_TOKEN,ROUND_URGENT_MS=ROUND_URGENT_TOKEN;
const ROUND_CLOCK_BOX=ROUND_CLOCK_BOX_TOKEN;
function roundRemainMs(){return Math.max(0,ROUND_LIMIT_MS-ROUND_MS)}
/* Rounded up, so the last whole second is spent showing 「1」 rather than
   showing 「0」 to somebody who still has a second to use. */
function roundLeft(){return Math.ceil(roundRemainMs()/1000)}
/* Only near the end, and only in a go somebody is playing. A countdown
   that runs the whole minute is an exam clock (条件①); one that runs
   behind the title screen or over a finished round is just noise. */
function roundClockDue(){
  if(ROUND_DONE||!ROUND_PLAYED_A_FRAME)return false;
  if(roundEnded())return false;
  return roundRemainMs()<ROUND_SHOW_MS}
function drawRoundClock(){if(!RCV||!roundClockDue())return;
  const c=RCV.getContext('2d'),W=RCV.width;
  const box=ROUND_CLOCK_BOX,urgent=roundRemainMs()<=ROUND_URGENT_MS;
  c.save();
  c.fillStyle='SCRIM_TOKEN'+'cc';
  c.fillRect(W-box[0],box[1],box[2],box[3]);
  /* The last three seconds are said in the alert colour rather than by
     blinking. §15's gate is about rapid alternation and a colour that
     changes once never approaches it - and 条件② asks for this to survive
     reduced motion, which it does by not being motion. It also does not
     say anything new: the number was already counting down. Whether the
     buzzer is a break or a defeat is E 節's question (C-1127) and this
     deliberately does not answer it - 「のこり」 says time is passing,
     not that anybody is losing. */
  c.fillStyle=urgent?'MAGENTA_TOKEN':'INK_TOKEN';
  c.textAlign='right';c.font='15px ui-monospace,monospace';
  c.fillText('のこり '+roundLeft(),W-16,box[1]+21);
  c.textAlign='left';c.restore()}
function roundClockFacts(){return {due:roundClockDue(),left:roundLeft(),
  remain:roundRemainMs(),urgent:roundRemainMs()<=ROUND_URGENT_MS,
  show:ROUND_SHOW_MS,urgentAt:ROUND_URGENT_MS,limit:ROUND_LIMIT_MS,
  played:ROUND_PLAYED_A_FRAME}}
/* --- 終盤の刻み、耳にも (§16 二重符号化, C-1448) ---------------------- */
/* C-1417 put the last seconds on the screen and C-1413 put the round's own
   ending in the hand. This is the same fact in the third channel, under
   the same two rules those two follow.
   Keyed to roundLeft() rather than to a timer of its own: the badge is
   already counting whole seconds, so the tick cannot drift away from the
   number a player is reading, and a slow frame - or two frames inside one
   millisecond - cannot double it up. One blip per whole second, three in
   all, and none of them any different from the others: the sound does not
   climb or quicken, because 「区切りか敗北か」 is the owner's question
   (C-1127, E 節) and a rising tick would have answered it.
   It asks sfx() rather than the audio context, which is how M and the
   volume dial (C-1408) are obeyed without this knowing about either. */
let ROUND_TICK_SAID=null;
function roundTickSound(){
  if(!roundClockDue()||roundRemainMs()>ROUND_URGENT_MS){ROUND_TICK_SAID=null;return}
  const left=roundLeft();
  /* 0 belongs to the buzzer, not to the countdown. */
  if(left<=0||left===ROUND_TICK_SAID)return;
  ROUND_TICK_SAID=left;
  try{sfx('tick')}catch(e){}}
function roundTickFacts(){return {said:ROUND_TICK_SAID}}
function drawRoundEnd(){if(!RCV)return;
  const c=RCV.getContext('2d'),W=RCV.width,H=RCV.height;
  c.save();c.fillStyle='SCRIM_TOKEN'+'cc';c.fillRect(0,H/2-52,W,104);
  c.fillStyle='INK_TOKEN';c.textAlign='center';
  c.font='22px ui-monospace,monospace';c.fillText('ここまで',W/2,H/2-10);
  /* The verdict lands at once; the ask waits out the quiet beat with the
     rest of the chrome (§6 観察 8, C-1382). R itself works throughout. */
  if(ROUND_END_FRAMES>ROUND_HOLD){
    c.font='13px ui-monospace,monospace';
    c.fillText('R / タップでもう一度',W/2,H/2+22)}
  c.textAlign='left';c.restore()}
/* The clock only ever fires over a game that had *not* finished, so there
   is no end screen to preserve: re-running the page is the whole restart,
   and it is the same one the tuning panel uses (C-1113). A template that
   ended on its own never gets here - its own R still owns that. */
/* The shield (§8 事実 3, C-1472): a player who was mashing when the buzzer
   arrived used to reload the page on the very next frame, never having seen
   「ここまで」, the reason line, or their own record. The whole restart is a
   `location.reload()`, so that press does not skip a screen - it destroys
   it. For ROUND_SHIELD frames after the buzzer, R and a tap are simply not
   counted as a restart; the press AFTER that is the immediate restart it
   always was. Nothing is queued: swallowing the mash and honouring the next
   press is what keeps this from becoming a delay somebody has to wait out.
   Only this clock's buzzer path is shielded - a template with an ending of
   its own owns its own R (kaiju, duel), and that is its screen to design. */
function roundShielded(){return ROUND_DONE&&ROUND_SHIELD_FRAMES<=ROUND_SHIELD}
function roundRestart(){if(!ROUND_DONE||roundShielded())return;
  try{if(typeof location!=='undefined'&&location&&typeof location.reload==='function'){
    location.reload()}}catch(e){}}
addEventListener('keydown',function(e){
  if(ROUND_DONE&&(e.key==='r'||e.key==='R')){roundRestart()}});
if(RCV){RCV.addEventListener('pointerdown',function(){if(ROUND_DONE){roundRestart()}})}
/* The ending's quiet beat (§6 観察 8, C-1382): the verdict - the
   template's own win/lose screen, or the clock's banner - lands at once,
   but the shared chrome waits 45 frames, so the fanfare (C-1326, ~30f)
   finishes over the scene it earned rather than under two bars of
   「R でもう一度」. The bank does NOT wait: it moves to the ending's
   first frame, so an R pressed inside the quiet still keeps the record. */
const ROUND_HOLD=45;
let ROUND_END_FRAMES=0;
/* Counted only over the buzzer, not over a template's own ending, so a game
   that finished by itself long before the clock cannot spend the shield on
   the player's behalf. */
const ROUND_SHIELD=ROUND_SHIELD_TOKEN;
let ROUND_SHIELD_FRAMES=0;
/* Outermost wrapper, installed after the pad: the banner has to be the last
   thing drawn, and holding the frame must not stop the loop. */
/* Counted AFTER the template's frame, in the same spot the strip used to
   draw: a template that ends on its very last scheduled frame still gets
   its bank on that frame (the old behaviour), and only the drawing
   waits. */
/* Templates ask through this (C-1384): their verdict and stats land at
   once, their own 「もう一度」 waits out the same quiet the strip does. */
function roundAskReady(){return ROUND_END_FRAMES>ROUND_HOLD}
function roundEndBeat(){
  if(ROUND_DONE||roundEnded()){
    if(ROUND_END_FRAMES===0){try{roundBank()}catch(e){}}
    ROUND_END_FRAMES++}
  else{ROUND_END_FRAMES=0}
  if(ROUND_DONE){ROUND_SHIELD_FRAMES++}else{ROUND_SHIELD_FRAMES=0}}
const ROUND_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return ROUND_RAF(function tick(t){
    roundTick(t);
    if(ROUND_DONE){roundEndBeat();drawRoundEnd();
      if(ROUND_END_FRAMES>ROUND_HOLD){drawResultStrip()}
      ROUND_RAF(tick);return}
    fn(t);
    roundEndBeat();
    /* Over the template's own frame, so the badge is not painted under the
       game (C-1417). It draws nothing at all until the last ten seconds. */
    drawRoundClock();
    /* The template drew its own ending; the strip goes on top of it,
       after the quiet beat. */
    if(roundEnded()&&ROUND_END_FRAMES>ROUND_HOLD){drawResultStrip()}})};
/* --- the result that leads back in (§8 事実 3) ------------------------ */
const ROUND_KEY='sidra.best.'+ROUND_NAME_TOKEN,ROUND_LABEL=ROUND_LABEL_TOKEN;
let ROUND_FINAL=null,ROUND_BEST=null,ROUND_RECORD=false,ROUND_BANKED=false;
/* The template's own counter, read where it lives. Guarded: a round that
   ends before the template has built its state must not throw on the way
   to the result screen. */
function roundScore(){try{const v=ROUND_SCORE_TOKEN;
  return (typeof v==='number'&&isFinite(v))?v:null}catch(e){return null}}
function roundBestRead(){try{if(typeof localStorage==='undefined')return null;
  const raw=localStorage.getItem(ROUND_KEY);if(raw===null)return null;
  const v=Number(raw);return isFinite(v)?v:null}catch(e){return null}}
function roundBestWrite(v){try{if(typeof localStorage!=='undefined'){
  localStorage.setItem(ROUND_KEY,String(v))}}catch(e){}}
function roundBest(){return ROUND_BEST}
/* Whether this result has anything to celebrate (C-1502, 第1回批評 #11).
   The bank and the cheer used to be the same flag: a first round is always
   a record because there is nothing to beat, so 0 点で全敗した初回が
   「自己ベスト更新」 - the strip congratulating a player on the worst run
   the game can produce. Measured on the real pages: duel 与ダメージ 0,
   fishing 得点 0 and platformer 宝石 0 all said it.
   The record itself is untouched. 0 is still written, still ghosted, still
   counted - it is a real result and the next round has to beat it. What is
   withheld is only the congratulation, and what the strip says instead is
   the honest line it already had for every other round: 自己ベスト 0
   （あと 1）.
   **Only the zero, not the defeat.** The item asked for defeats to be
   excluded too, on the reading that losing is nothing to celebrate. Driven
   against the real pages, that reading is wrong here: most of these
   templates END in defeat by design - you play until you die - so
   ``roundLost()`` is true for an ordinary good run. Excluding it silenced
   the record on shooter 得点 54, puzzle 得点 36, adventure 宝石 1 and
   marble スコア 1, all of them genuine firsts. A round you scored in and
   then lost is still your best round. What was never a best is a round
   that beat nothing. */
function roundCheer(){
  if(!ROUND_RECORD)return false;
  return ROUND_FINAL!==null&&ROUND_FINAL>0}
/* The last few runs, in the order they happened (C-1432). A best is one
   number and it only moves upward, so a page that keeps nothing else can
   say 「自己ベスト 24（あと 5）」 for an hour without ever telling a player
   that they are getting closer. The sequence is what shows a day's
   progress on the days the record does not move.
   * Kept exactly the way the best is: this device's localStorage, nothing
     sent, no URL - the boundary the panel and the index sit inside.
   * Written as it happened. A run that went worse stays in the row: a
     sequence that quietly dropped its bad days would be flattery, and
     nobody could use it to tell whether they are improving.
   * Only rounds somebody played. The untouched guard in roundBank() is
     above this for the same reason it is above the best. */
const ROUND_LOG_KEY='sidra.runs.'+ROUND_NAME_TOKEN,ROUND_LOG_MAX=5;
let ROUND_LOG=[];
function roundLogRead(){try{if(typeof localStorage==='undefined')return [];
  const raw=localStorage.getItem(ROUND_LOG_KEY);if(raw===null)return [];
  const list=JSON.parse(raw);
  if(!Array.isArray(list))return [];
  return list.filter(v=>typeof v==='number'&&isFinite(v)).slice(-ROUND_LOG_MAX)}
  catch(e){return []}}
function roundLogWrite(list){try{if(typeof localStorage!=='undefined'){
  localStorage.setItem(ROUND_LOG_KEY,JSON.stringify(list))}}catch(e){}}
/* Re-read before appending rather than trusting the copy in memory: two
   tabs of the same page would otherwise each keep their own row and the
   last one to finish would erase the other's. */
function roundLogPush(v){const list=roundLogRead();list.push(v);
  ROUND_LOG=list.slice(-ROUND_LOG_MAX);roundLogWrite(ROUND_LOG)}
function roundLog(){return ROUND_LOG.slice()}
function roundLogFacts(){return {runs:roundLog(),max:ROUND_LOG_MAX,
  stored:roundLogRead()}}
ROUND_LOG=roundLogRead();
/* --- the second key, for a score with a ceiling (C-1124) ------------- */
const ROUND_TIE_KEY='sidra.tie.'+ROUND_NAME_TOKEN;
const ROUND_TIE_BETTER=ROUND_TIE_BETTER_TOKEN,ROUND_TIE_LABEL=ROUND_TIE_LABEL_TOKEN;
let ROUND_TIE=null,ROUND_TIE_BEST=null;
/* Guarded like roundScore: a round that ends before the template built its
   state must not throw on the way to the result screen. */
function roundTieNow(){try{const v=ROUND_TIE_TOKEN;
  return (typeof v==='number'&&isFinite(v))?v:null}catch(e){return null}}
function roundTieRead(){try{if(typeof localStorage==='undefined')return null;
  const raw=localStorage.getItem(ROUND_TIE_KEY);if(raw===null)return null;
  const v=Number(raw);return isFinite(v)?v:null}catch(e){return null}}
function roundTieWrite(v){try{if(typeof localStorage!=='undefined'){
  localStorage.setItem(ROUND_TIE_KEY,String(v))}}catch(e){}}
/* Only consulted when the scores are level - the score is still the
   score. Without a tiebreak this returns false and nothing changes, which
   is what the six templates that have no ceiling get. */
function roundTieBeats(now,best){
  if(!ROUND_TIE_BETTER||now===null)return false;
  if(best===null)return true;
  return ROUND_TIE_BETTER==='less'?now<best:now>best}
function roundTieFacts(){return {now:ROUND_TIE,best:ROUND_TIE_BEST,
  better:ROUND_TIE_BETTER,label:ROUND_TIE_LABEL}}
/* Banked once per round, on the first frame it is over: reading the score
   every frame afterwards would keep overwriting the best with whatever the
   frozen page still holds. Kept on this device only - no URL, nothing
   sent, the same boundary the tuning panel and the index sit inside. */
function roundBank(){if(ROUND_BANKED)return;
  /* Behind the title there is no round to bank: what the demo did is the
     demo's (C-1414). Checked before the flag is set and before the score is
     read, because both of those outlive the frame - the untouched guard
     below already refuses to *write* anything, but it comes after
     ROUND_FINAL has been filled in, and a demo's lap count sitting in
     ROUND_FINAL is the number the player's own first result strip would
     print. */
  try{if(gateState()==='title')return}catch(e){}
  ROUND_BANKED=true;
  ROUND_FINAL=roundScore();ROUND_BEST=roundBestRead();
  if(ROUND_FINAL===null)return;
  /* Nobody played, so there is nothing to credit anybody with (C-1123).
     The score is still shown - it is what happened - but it is not banked
     as a best, not counted toward a colour, not kept as a ghost, and not
     recorded as a win or a loss. */
  if(!ROUND_TOUCHED)return;
  /* Into the row before anything is judged: the sequence is what happened,
     not what was good enough (C-1432). */
  roundLogPush(ROUND_FINAL);
  /* And the day is counted here, under the same guard: a day nobody
     played is not a day you came back (C-1442). */
  try{dailyStreakBank()}catch(e){}
  /* The round confirming itself, in the third sense (C-1413, §16): two
     short taps, after the guard above, so a round nobody played stays
     silent in the hand as well as in the records. */
  try{haptic(ROUND_HAPTIC_TOKEN)}catch(e){}
  ROUND_TIE=roundTieNow();ROUND_TIE_BEST=roundTieRead();
  if(ROUND_BEST===null||ROUND_FINAL>ROUND_BEST){ROUND_RECORD=true;
    roundBestWrite(ROUND_FINAL);ROUND_BEST=ROUND_FINAL;
    if(ROUND_TIE!==null){roundTieWrite(ROUND_TIE);ROUND_TIE_BEST=ROUND_TIE}}
  /* A score with a ceiling is reached and then never beaten, so the run
     that reaches it faster - or with more left - is the better run
     (C-1124). Only when the scores are level: this breaks ties, it does
     not outrank the score. */
  else if(ROUND_FINAL===ROUND_BEST&&roundTieBeats(ROUND_TIE,ROUND_TIE_BEST)){
    ROUND_RECORD=true;roundTieWrite(ROUND_TIE);ROUND_TIE_BEST=ROUND_TIE}
  /* The same number, banked a second way: the best is this round against
     the last one, the total is every round there has ever been (C-1109).
     Both stay on this device. */
  try{skinBank(ROUND_FINAL)}catch(e){}
  /* The trail that set this record, kept with the number (C-1401). */
  try{ghostBank(ROUND_RECORD)}catch(e){}
  /* Won or lost, for the run after this one (C-1402), and it has to be a
     real defeat (C-1122). "Any failure beat fired" was the wrong question
     twice over: the count ran for the life of the page, and the clock's
     own beat made every fishing and catch round a defeat - those two have
     no losing state at all, so the buzzer is how a go ends, not how it is
     lost. Counting it would ease the difficulty for every player after
     three rounds, which is precisely the help-for-people-who-don't-need-it
     §11 事実 3 warns about. The beat itself is untouched: an ending should
     still land (C-1105). */
  try{adaptRecord(roundLost())}catch(e){}}
/* One strip, drawn over whatever ended the round - the clock's banner or
   the template's own screen - so "how far off am I, and how do I go
   again" reads the same everywhere. */
function drawResultStrip(){if(!RCV)return;roundBank();
  const c=RCV.getContext('2d'),W=RCV.width,H=RCV.height;
  /* Two lines, not one. Each of C-1104, C-1106, C-1107 and C-1110 added a
     clause to this strip while the others were switched off; with all four
     on it measured about 800px on a 720px canvas, and being centred it lost
     both ends - the daily stamp on the left and the copy hint on the right.
     Found by C-1118's sweep, which is the only run that had them all on. */
  c.save();c.fillStyle='SCRIM_TOKEN'+'e6';c.fillRect(0,H-52,W,52);
  c.fillStyle='INK_TOKEN';c.textAlign='center';
  c.font='13px ui-monospace,monospace';
  let left='';
  if(ROUND_FINAL!==null){
    left=ROUND_LABEL+' '+ROUND_FINAL;
    if(roundCheer()){left+=' / 自己ベスト更新'}
    else if(ROUND_BEST!==null&&ROUND_FINAL===ROUND_BEST&&ROUND_TIE_BETTER
      &&ROUND_TIE_BEST!==null){
      /* The score is maxed out, so 「あと 1」 would be a target nobody can
         reach. What is left to beat is the second key (C-1124). */
      left+=' / '+ROUND_TIE_LABEL+' '+ROUND_TIE+'（自己ベスト '+ROUND_TIE_BEST+'）'}
    else if(ROUND_BEST!==null){left+=' / 自己ベスト '+ROUND_BEST
      +'（あと '+(ROUND_BEST-ROUND_FINAL+1)+'）'}}
  /* Whose board this was. Only when the switch is on: a line that always
     said 今日の挑戦 would make the shared attempt meaningless. */
  let mark='';
  try{if(dailyBoard()){mark='今日の挑戦 '+dailyStamp();
    /* Only once it is a run of days. On the first one 「1 日目」 would be
       a streak of one, which is just today with a number on it - the same
       reason the runs row waits for a second run (C-1432). */
    const days=dailyStreak();if(days>1){mark+='（'+days+' 日目）'}
    mark+='   '}}catch(e){}
  /* The copy key is offered only where there is something to copy. */
  let right='R / タップでもう一度';
  try{if(shareReady()){right+='   C / 結果をコピー'}}catch(e){}
  /* What happened on top, what to do next underneath. */
  if(mark||left){c.fillText(mark+left,W/2,H-32)}
  c.fillText(right,W/2,H-12);
  /* And, on a loss the template can account for, why (C-1409). Above the
     score line so the order reads cause, result, next - and only when
     there is a counted reason to give. */
  let why='';try{why=recapLine()}catch(e){}
  if(why){c.fillStyle='SCRIM_TOKEN'+'e6';c.fillRect(0,H-72,W,22);
    c.fillStyle='INK_TOKEN';c.fillText(why,W/2,H-56)}
  /* A colour that just opened is the reason to start the next round, so it
     is said on the screen that asks for one - and only when it happened. */
  /* The last few runs, small and to one side (C-1432). Two is the fewest
     that can be a sequence - a row of one is just the score again, said
     twice - and it is drawn under the score rather than beside it so the
     result keeps the line it had. */
  let runs=[];try{runs=roundLog()}catch(e){}
  if(runs.length>1){c.save();c.font='13px ui-monospace,monospace';
    c.textAlign='left';c.globalAlpha=0.72;
    c.fillText('直近 '+runs.join(' / '),16,H-42);c.restore()}
  let news=null;try{news=skinNews()}catch(e){}
  if(news){c.fillStyle='SCRIM_TOKEN'+'e6';c.fillRect(0,H-82,W,30);
    c.fillStyle=TUNE_ACCENT;
    c.fillText('新しい見た目「'+news+'」が開きました',W/2,H-62)}
  c.textAlign='left';c.restore()}
function roundFacts(){return {ms:ROUND_MS,done:ROUND_DONE,reason:ROUND_REASON,
  tie:roundTieFacts(),
  endFrames:ROUND_END_FRAMES,hold:ROUND_HOLD,banked:ROUND_BANKED,
  shieldFrames:ROUND_SHIELD_FRAMES,shield:ROUND_SHIELD,shielded:roundShielded(),
  ended:roundEnded(),limit:ROUND_LIMIT_MS,
  score:ROUND_FINAL,best:ROUND_BEST,record:ROUND_RECORD,
  cheer:(function(){try{return roundCheer()}catch(e){return null}})(),
  lost:(function(){try{return roundLost()}catch(e){return null}})(),
  live:roundScore(),
  runs:(function(){try{return roundLog()}catch(e){return null}})(),
  seed:(typeof SEED==='undefined')?null:SEED,
  daily:(function(){try{return dailyOn()}catch(e){return null}})(),
  stamp:(function(){try{return dailyStamp()}catch(e){return null}})(),
  state:(typeof state==='undefined')?null:state}}
"""


#: Runs a generated page for longer than the bound, pressing start once and
#: nothing after that. "A go ends" is a claim about a page left alone, so
#: the probe leaves it alone.
PROBE = KEY_EVENT_JS + """
const roundNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : roundNothing),
  apply: () => roundNothing, set: () => true });
const roundKeys = [];
let roundReloads = 0;
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
/* The date is pinned so "today's challenge" can be observed twice on the
   same day and once on the next, which is the whole claim. */
class RoundDate {
  constructor(){ return RoundDate.parse() }
  static parse(){ const [y, m, d] = 'STAMP_INPUT'.split('-').map(Number);
    return { getFullYear: () => y, getMonth: () => m - 1, getDate: () => d } }
}
globalThis.Date = RoundDate;
let roundClock = 0;
globalThis.performance = { now: () => roundClock };
const roundPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') roundKeys.push(fn) };
globalThis.Image = function(){ return roundNothing };
const roundStore = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in roundStore ? roundStore[k] : null),
  setItem(){}, removeItem(){} };
/* A recording context, not the swallowing Proxy: "an immediate retry
   prompt" is a claim about words on the screen, and only a recorder can
   see them. */
const roundText = [];
globalThis.location = { reload: () => { roundReloads++ } };
globalThis.document = { readyState: 'complete',
  createElement: () => roundNothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {},
    addEventListener: (type, fn) => {
      if (type === 'pointerdown') roundPointers.push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    /* C-1130: the colour every fill was made with, kept beside what it
       drew. The shared chrome used to paint itself in the dark theme's own
       ink whatever palette the page was in, and a stub that threw
       fillStyle away could not have noticed. */
    getContext: () => new Proxy({
      fillText: (t) => { roundText.push(String(t)); roundPaint.push(['text', roundInk, String(t)]) },
      fillRect: () => { roundPaint.push(['rect', roundInk, '']) } }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : roundNothing)),
      set: (t, k, v) => { if (k === 'fillStyle') { roundInk = String(v) } return true } }) }) };
let roundPaint = [], roundInk = null;
let roundQueued = null;
globalThis.requestAnimationFrame = (fn) => { roundQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* 16.67ms a frame, the timestamp the page reads for its own clock. */
function roundRun(frames){
  for (let i = 0; i < frames && roundQueued; i++) {
    const fn = roundQueued; roundQueued = null;
    roundClock += 50 / 3;
    fn(roundClock);
  }
}
/* Frames spent on the title screen before anything is pressed. The gate
   holds the template's callback back, so these must cost the round
   nothing - that is the difference between played time and wall time. */
roundRun(WARMUP_INPUT);
const beforePress = roundFacts().ms;
const press = probeKey(' ');
roundKeys.forEach(fn => fn(press));
let firstBreak = null;
const roundHeld = HOLD_INPUT;
for (let f = 0; f < FRAMES_INPUT; f++) {
  if (roundHeld) { roundKeys.forEach(fn => fn({ key: roundHeld, code: roundHeld,
    preventDefault(){}, stopImmediatePropagation(){} })) }
  roundRun(1);
  const now = roundFacts();
  /* Labelled here rather than read from ROUND_REASON: the clock writes that
     at the top of the *next* tick, and a template that stops scheduling
     when it ends never gets one. */
  if (firstBreak === null && (now.done || now.ended)) {
    firstBreak = { ms: now.ms, by: now.done ? 'time' : 'template', state: now.state,
      beats: failBeats(), shake: shakeAmount(), frame: f };
    roundText.length = 0;
  }
}
/* Coming back: one tap, then R. §8 事実 3 asks for a single tap from the
   result, so the tap is tried first and the state is read after each. */
const end = roundFacts();
const roundStrip = roundText.slice(-6);
roundPointers.forEach(fn => fn({ pointerType: 'touch', pointerId: 1,
  clientX: 360, clientY: 160, preventDefault(){}, stopImmediatePropagation(){} }));
roundRun(2);
const afterTap = { live: roundLive(), ended: roundEnded(), reloads: tuneProbeReloadsShim() };
roundKeys.forEach(fn => fn({ key: 'r', code: 'KeyR',
  preventDefault(){}, stopImmediatePropagation(){} }));
roundRun(2);
const afterKey = { live: roundLive(), ended: roundEnded(), reloads: tuneProbeReloadsShim() };
/* A template that restarts in place is now in a *new* round, and the bank
   for the old one has to be shut: a strip - or a line to paste - still
   reporting the previous score would be reporting a round nobody is
   playing. Null here means the bank was cleared. */
const afterRestart = roundFacts().score;
function tuneProbeReloadsShim(){ return roundReloads }
console.log(JSON.stringify({
  gatedMs: beforePress,
  beatsAtBreak: firstBreak ? firstBreak.beats : null,
  shakeAtBreak: firstBreak ? firstBreak.shake : null,
  beatsTotal: failBeats(),
  /* Only what was drawn after the break: the retry line has to be up
     within a second or two of losing, not somewhere in the whole run. */
  saidAfter: roundText.slice(0, 400),
  /* The tail, not the head: the banner is drawn at the break, and the
     game's own fills would fill a head-anchored window long before. */
  paint: roundPaint.slice(-600),
  strip: roundStrip,
  score: end.score, best: end.best, record: end.record, liveScore: end.live,
  /* The record and the congratulation, apart (C-1502): a run can set one
     without earning the other, and a probe that reported only `record`
     could not tell the fix from the bug. */
  cheer: end.cheer, lost: end.lost,
  seed: end.seed, daily: end.daily, stamp: end.stamp,
  afterTap: afterTap, afterKey: afterKey, afterRestart: afterRestart,
  breakAt: firstBreak ? firstBreak.ms : null,
  reason: firstBreak ? firstBreak.by : null,
  endState: firstBreak ? firstBreak.state : null,
  running: roundQueued !== null,
  limit: end.limit,
  reloads: roundReloads,
}));
"""


def probe_source(
    script: str,
    *,
    frames: int = 4200,
    warmup: int = 4,
    reduced: bool = False,
    stored: dict[str, dict] | None = None,
    stamp: str = "2026-09-03",
    hold: str | None = None,
) -> str:
    """The page's own script, started once and then left alone.

    ``warmup`` is how many frames sit on the title screen before the
    single press. Those frames have to cost the round nothing.

    ``hold`` presses one key every frame, which since C-1123 is the
    difference between a round somebody played and a round that merely
    ran: an abandoned one banks no best, no total and no streak, so a
    check about *records* has to hold a key to be about anything.
    """

    payload = {key: json.dumps(value, ensure_ascii=False) for key, value in (stored or {}).items()}
    return (
        PROBE.replace("FRAMES_INPUT", str(int(frames)))
        .replace("WARMUP_INPUT", str(int(warmup)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("STAMP_INPUT", stamp)
        .replace("HOLD_INPUT", json.dumps(hold))
        .replace("STORED_INPUT", json.dumps(payload, ensure_ascii=False))
        .replace("SCRIPT_PLACEHOLDER", script)
    )


#: When the countdown appears, and when it starts being said in the alert
#: colour. Ten seconds because §8 事実 1 asks for a break inside about a
#: minute and a break you cannot see coming is not a break, it is a
#: surprise - and *not* sixty, because a clock that runs the whole go turns
#: 「気楽な 1 分」 into an exam (C-1417 条件①).
ROUND_SHOW_MS = 10_000
ROUND_URGENT_MS = 3_000

#: How long a break in the frames has to be before the clock stops charging
#: for it (C-1450). One second, taken from the neighbour rather than from
#: taste: music.py re-anchors its scheduler on the same gap. It is 60 frames
#: at 60fps - far past any stutter or long paint, and far short of anything
#: a person would notice as a pause - and hitstop does not reach it either,
#: because hitstop withholds the drawing while the loop keeps running.
ROUND_GAP_MS = 1_000

#: Frames after the buzzer during which R and a tap are not a restart
#: (C-1472). 24 frames is ~400ms at 60fps: long enough that a mash carried
#: through the buzzer does not erase the result, short enough that anybody
#: who looked up and then pressed feels nothing. It expires well before
#: ``ROUND_HOLD`` (45) puts 「R / タップでもう一度」 on the screen, so the
#: shield is invisible to a player who waits for the prompt.
ROUND_SHIELD_FRAMES = 24

#: Where the badge goes: the band directly under the templates' own HUD
#: row, on the right. Chosen by measurement rather than by eye - every
#: template was driven and its paint recorded, and this band is the only
#: one that carries no text in any of the ten. The corners do not qualify:
#: seven templates print their score at the top left, kaiju and racing
#: print at the top right, three print at the bottom left, and the
#: on-screen pad owns the bottom right on a phone. Measured on a played
#: frame per template, so a warning that only appears in some other moment
#: could still land here; the badge draws its own scrim so it stays
#: readable if one does.
ROUND_CLOCK_BOX = (96, 44, 88, 30)


def preamble_for(template: str) -> str:
    """The clock and the result strip, told about one template."""

    expression, label = ROUND_SCORE.get(template, ("null", "得点"))
    tie_expression, better, tie_label = ROUND_TIE.get(template, ("null", "", ""))
    return (
        ROUND_PREAMBLE.replace(
            "ROUND_LIVE_TOKEN", json.dumps(list(ROUND_LIVE.get(template, ())))
        )
        .replace("ROUND_LIMIT_TOKEN", str(ROUND_SECONDS * 1000))
        .replace("ROUND_SHOW_TOKEN", str(ROUND_SHOW_MS))
        .replace("ROUND_URGENT_TOKEN", str(ROUND_URGENT_MS))
        .replace("ROUND_GAP_TOKEN", str(ROUND_GAP_MS))
        .replace("ROUND_SHIELD_TOKEN", str(ROUND_SHIELD_FRAMES))
        .replace("ROUND_CLOCK_BOX_TOKEN", json.dumps(list(ROUND_CLOCK_BOX)))
        .replace("ROUND_HAPTIC_TOKEN", json.dumps(list(HAPTIC_ROUND)))
        .replace("ROUND_NAME_TOKEN", json.dumps(template))
        .replace("ROUND_LABEL_TOKEN", json.dumps(label, ensure_ascii=False))
        .replace("ROUND_SCORE_TOKEN", expression)
        .replace("ROUND_TIE_TOKEN", tie_expression)
        .replace("ROUND_TIE_BETTER_TOKEN", json.dumps(better))
        .replace("ROUND_TIE_LABEL_TOKEN", json.dumps(tie_label, ensure_ascii=False))
    )


__all__ = [
    "HOLD_PROBE",
    "hold_probe_source",
    "PREAMBLE_NAMES",
    "MASH_PROBE",
    "PROBE",
    "SHIELD_PROBE",
    "TICK_PROBE",
    "ROUND_LIVE",
    "ROUND_SCORE",
    "ROUND_TIE",
    "ROUND_PREAMBLE",
    "ROUND_SECONDS",
    "ROUND_GAP_MS",
    "ROUND_SHIELD_FRAMES",
    "live_gaps",
    "mash_probe_source",
    "shield_probe_source",
    "tick_probe_source",
    "preamble_for",
    "probe_source",
    "states_in",
]


#: One round on one page load, against a store handed in from the last one
#: (C-1432). Restarting is a real ``location.reload()``, so several rounds
#: cannot share a page: each is its own process, and what carries between
#: them is exactly what carries in a browser - the store.
#:
#: The other probes here stub ``setItem`` away, which is right for them:
#: they ask what one round does. A row of recent runs is a claim about what
#: survives *between* rounds, so it can only be measured against a store
#: that remembers, and across loads that really are separate.
HISTORY_PROBE = KEY_EVENT_JS + """
const hNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : hNothing),
  apply: () => hNothing, set: () => true });
const hKeys = [];
globalThis.matchMedia = () => ({ matches: false });
let hClock = 0;
globalThis.performance = { now: () => hClock };
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') hKeys.push(fn) };
globalThis.Image = function(){ return hNothing };
/* Seeded with whatever the previous load left behind, and it keeps what
   this one writes. */
const hStore = STORE_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in hStore ? hStore[k] : null),
  setItem: (k, v) => { hStore[k] = String(v) },
  removeItem: (k) => { delete hStore[k] } };
const hDrawn = [];
const hCtx = new Proxy({ fillText: (t) => { hDrawn.push(String(t)) } },
  { get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : hNothing)),
    set: () => true });
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => hNothing, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => hCtx }) };
globalThis.location = { reload: () => {} };
let hQueued = null;
globalThis.requestAnimationFrame = (fn) => { hQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function hKey(k){ const e = probeKey(k);
  hKeys.forEach(fn => fn(e)) }
/* Bigger steps than a real frame, so a sixty-second round does not need
   thirty-six hundred of them. The clock the round reads is this one. */
function hStep(n, hold){ for (let i = 0; i < n && hQueued; i++) {
  if (hold) { hKey(hold) }
  const fn = hQueued; hQueued = null; hClock += STEP_INPUT; fn(hClock) } }
const hHold = HOLD_INPUT;
/* What the row looked like before this round, so the judge can see the
   append rather than only the result. */
const before = roundLogFacts();
hKey(' ');
hStep(2, null);
/* A round is over when the TEMPLATE ends it or when the CLOCK does, and
   this loop used to ask only the first (C-1506). Two ways that was wrong,
   both measured rather than reasoned about:
   * fishing and catch have no end state at all - ``ROUND_LIVE`` is empty,
     so ``roundEnded()`` is structurally false forever;
   * and for every other template it never fired either, because the buzzer
     arrives first and the wrapper then stops calling the template's frame,
     freezing it in a live state.
   So the break was dead code on all ten and the loop ran its full 4000
   every time, working only because the guard outlasted the round. Asking
   both questions - the pair ``share.py`` and ``adapt.py`` already ask - is
   what makes the guard a guard again instead of the exit. */
/* Named off `guard` for the same reason the hold probe is (C-1637):
   adventure's page owns that word. This probe only drives catch today,
   so the clash is latent - and a latent trap is still a trap. */
let hsGuard = 0;
while (hsGuard++ < 4000) {
  hStep(1, hHold);
  let done = false;
  try { done = roundEnded() || ROUND_DONE } catch (e) { done = false }
  if (done) break;
}
/* The strip is what banks the round, so let it draw - and the strip waits
   out the ending's quiet beat (``ROUND_HOLD``, 45 frames) before it paints.
   Six steps used to be enough only because the loop above overran by
   ~3,760 iterations and spent the beat by accident; now that it stops at
   the buzzer, the wait has to be asked for (C-1506). */
hDrawn.length = 0;
hStep(60, null);
const facts = roundFacts();
console.log(JSON.stringify({
  score: facts.score, best: facts.best,
  touched: (function(){ try { return roundTouched() } catch (e) { return null } })(),
  before: before.runs, runs: roundLogFacts().runs,
  stored: roundLogFacts().stored, max: roundLogFacts().max,
  said: hDrawn.filter(t => t.indexOf('直近') === 0),
  drawn: hDrawn.slice(0, 40),
  store: hStore,
}));
"""


#: The quiet beat, watched (§6 観察 8, C-1382): the round is played to its
#: break, and the strip must be absent just after it, present after the
#: hold - while the bank has already happened inside the quiet.
HOLD_PROBE = KEY_EVENT_JS + """
const roundNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : roundNothing),
  apply: () => roundNothing, set: () => true });
const roundKeys = [];
globalThis.matchMedia = () => ({ matches: false });
let roundClock = 0;
globalThis.performance = { now: () => roundClock };
const roundPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') roundKeys.push(fn) };
globalThis.Image = function(){ return roundNothing };
const roundStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in roundStore ? roundStore[k] : null),
  setItem: (k, v) => { roundStore[k] = String(v) },
  removeItem: (k) => { delete roundStore[k] } };
const roundText = [];
globalThis.location = { reload(){} };
globalThis.document = { readyState: 'complete',
  createElement: () => roundNothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {},
    addEventListener: (type, fn) => {
      if (type === 'pointerdown') roundPointers.push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => new Proxy({
      fillText: (t) => { roundText.push(String(t)) },
      fillRect: () => {} }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : roundNothing)),
      set: () => true }) }) };
let roundQueued = null;
globalThis.requestAnimationFrame = (fn) => { roundQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function roundRun(frames){
  for (let i = 0; i < frames && roundQueued; i++) {
    const fn = roundQueued; roundQueued = null;
    roundClock += 50 / 3;
    fn(roundClock);
  }
}
function roundKey(k){ roundKeys.forEach(fn => fn(probeKey(k))) }
/* Through the gate, then one real cast so the round is somebody's. */
roundKey(' ');
roundRun(30);
roundKey(' ');
/* To the break. */
/* Not `guard`: adventure's page owns that name for its guardian, and a
   top-level `let` of it makes the whole probe a SyntaxError - one of ten
   templates was unmeasurable because the instrument took a word the page
   was using (C-1637). */
let hdGuard = 0;
while (!(roundFacts().done || roundFacts().ended) && hdGuard++ < 12000) roundRun(1);
const atEnd = roundFacts();
/* The shared strip's own marker: only it says 自己ベスト. A template's
   verdict screen may carry its own retry line - that is the verdict, and
   the claim leaves it immediate; the quiet is about the shared chrome. */
const strip = (line) => line.indexOf('自己ベスト') >= 0;
const ask = (line) => line.indexOf('もう一度') >= 0;
/* Just inside the quiet: no chrome, but the bank already closed. */
roundText.length = 0;
roundRun(10);
const early = { strip: roundText.some(strip), ask: roundText.some(ask),
  banked: roundFacts().banked,
  bestKept: Object.keys(roundStore).some(k => k.indexOf('sidra.best.') === 0) };
/* Past the hold: the chrome arrives. */
roundRun(50);
const late = { strip: roundText.some(strip), ask: roundText.some(ask),
  endFrames: roundFacts().endFrames };
console.log(JSON.stringify({ broke: atEnd.done || atEnd.ended,
  hold: atEnd.hold, early: early, late: late, score: roundFacts().score }));
"""


def hold_probe_source(script: str) -> str:
    """The page's own script, wrapped so the quiet beat can be watched."""

    return HOLD_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def history_probe_source(
    script: str,
    *,
    store: dict[str, str] | None = None,
    hold: str | None = "ArrowRight",
    step: int = 250,
) -> str:
    """One page load: play a round (or leave it alone) and read the row.

    ``store`` is what the previous load left behind. ``hold`` of ``None`` is
    the round nobody played - the fourth condition the item set.
    """

    return (
        HISTORY_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("STORE_INPUT", json.dumps(store or {}, ensure_ascii=False))
        .replace("HOLD_INPUT", json.dumps(hold))
        .replace("STEP_INPUT", str(int(step)))
    )


#: Runs a generated page for a whole go and writes down, frame by frame,
#: whether the countdown said it was due and what it actually painted. Both
#: halves are needed: "due" is the page's own opinion and the painted text
#: is what a player sees, and C-1415's break table has an example of those
#: two coming apart (the condition decided correctly, the element never
#: touched).
CLOCK_PROBE = KEY_EVENT_JS + """
const clkNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : clkNothing),
  apply: () => clkNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT,
  addEventListener(){}, addListener(){} });
let clkTime = 0;
globalThis.performance = { now: () => clkTime };
const clkKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') clkKeys.push(fn) };
globalThis.Image = function(){ return clkNothing };
const clkStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in clkStore ? clkStore[k] : null),
  setItem: (k, v) => { clkStore[k] = String(v) }, removeItem: (k) => { delete clkStore[k] } };
globalThis.location = { reload: () => {} };
let clkPaint = [], clkInk = null;
const clkEl = { width: 720, height: 320, style: {}, textContent: '', attrs: {}, handlers: {},
  addEventListener(){}, setAttribute(){}, getAttribute(){ return null }, blur(){},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    fillText: (s, x, y) => { clkPaint.push({ s: String(s), x: Math.round(Number(x) || 0),
      y: Math.round(Number(y) || 0), ink: clkInk }) },
    fillRect: () => {} }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : clkNothing)),
    set: (t, k, v) => { if (k === 'fillStyle') { clkInk = String(v) } return true } }) };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => clkEl, querySelector: () => null, getElementById: () => clkEl };
let clkQueued = null;
globalThis.requestAnimationFrame = (fn) => { clkQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* Through the gate first: the clock does not start until play does. */
function clkStep(){ if (!clkQueued) return null;
  const fn = clkQueued; clkQueued = null; clkPaint = []; clkTime += 50 / 3; fn(clkTime);
  return clkPaint.filter(op => op.s.indexOf('のこり') === 0) }
clkStep(); clkStep();
clkKeys.forEach(fn => fn(probeKey(' ')));
const seen = [];
const clkHold = HOLD_INPUT;
for (let f = 0; f < FRAMES_INPUT; f++) {
  /* Some templates end on their own long before the buzzer when nobody
     touches them - a duel both sides refuse to fight is over in seconds.
     Holding a key keeps the go alive far enough in to reach the clock. */
  if (clkHold) { clkKeys.forEach(fn => fn({ key: clkHold, code: clkHold,
    preventDefault(){}, stopImmediatePropagation(){} })) }
  /* A hidden tab, as the page would actually see it (C-1450): no frames at
     all for a while, then one frame carrying the whole absence in its
     timestamp. Injected into the clock rather than into the loop, because
     that is exactly what requestAnimationFrame does when it wakes. */
  if (GAP_MS_INPUT && f === GAP_AT_INPUT) { clkTime += GAP_MS_INPUT }
  const painted = clkStep();
  if (painted === null) break;
  const facts = roundClockFacts();
  seen.push({ ms: facts.remain, due: facts.due, left: facts.left,
    /* Why the go ended, so "the buzzer fired for time nobody played" is a
       read fact rather than an inference from the clock. */
    reason: roundFacts().reason, clock: clkTime,
    /* Every fill on this frame, not only the badge's. A frame that painted
       nothing at all is a frozen picture - the canvas still shows the last
       one - and that is a very different thing from a frame that redrew
       the game and left the badge off it. */
    all: clkPaint.length,
    urgent: facts.urgent, done: roundFacts().done,
    /* What a player would read, and the colour it was in. */
    said: painted.length ? painted[0].s : null,
    ink: painted.length ? painted[0].ink : null,
    at: painted.length ? [painted[0].x, painted[0].y] : null,
    n: painted.length });
}
console.log(JSON.stringify({ frames: seen,
  show: roundClockFacts().show, urgentAt: roundClockFacts().urgentAt,
  limit: roundClockFacts().limit }));
"""


#: The last seconds in the ear (C-1448). Built on the clock probe above -
#: same fake page, same whole go - with a recording AudioContext in place of
#: the silence, so what is read back is the sound the page actually built
#: rather than the call it made. That distinction is the point of the mute
#: run: muted, ``sfx`` returns before it touches the context, so a page that
#: obeys M records zero nodes while still asking once a second.
TICK_PROBE = KEY_EVENT_JS + """
const tkNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : tkNothing),
  apply: () => tkNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false, addEventListener(){}, addListener(){} });
let tkTime = 0;
globalThis.performance = { now: () => tkTime };
/* Every sound the page BUILDS, with the note it started on: an effect that
   is asked for while muted never reaches here, which is how the mute run
   tells "asked and refused" from "never asked". */
const tkBuilt = [];
function TkContext(){ this.state='running'; this.currentTime=0; this.destination={};
  this.sampleRate=44100 }
TkContext.prototype.createPeriodicWave = function(){ return { kind:'wave' } };
TkContext.prototype.createOscillator = function(){
  const note = { hz: null, to: null };
  tkBuilt.push(note);
  return { type:'', setPeriodicWave(){},
    frequency:{ kind:'frequency', setValueAtTime(v){ note.hz = Number(v) },
      exponentialRampToValueAtTime(v){ note.to = Number(v) } },
    connect(){}, start(){}, stop(){} } };
TkContext.prototype.createBuffer = function(ch, len){
  return { getChannelData: () => new Float32Array(len) } };
TkContext.prototype.createBufferSource = function(){
  return { buffer:null, start(){}, stop(){}, connect(){} } };
TkContext.prototype.createBiquadFilter = function(){
  return { kind:'lowpass', type:'',
    frequency:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} }, connect(){} } };
TkContext.prototype.createGain = function(){
  return { gain:{ setValueAtTime(v){ tkBuilt.push({ gain: Number(v) }) },
      exponentialRampToValueAtTime(){}, value: 0 },
    connect(){} } };
globalThis.window = { AudioContext: TkContext };
const tkKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') tkKeys.push(fn) };
globalThis.Image = function(){ return tkNothing };
const tkStore = STORE_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in tkStore ? tkStore[k] : null),
  setItem: (k, v) => { tkStore[k] = String(v) }, removeItem: (k) => { delete tkStore[k] } };
globalThis.location = { reload: () => {} };
const tkEl = { width: 720, height: 320, style: {}, textContent: '', attrs: {}, handlers: {},
  addEventListener(){}, setAttribute(){}, getAttribute(){ return null }, blur(){},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => tkNothing };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => tkEl, querySelector: () => null, getElementById: () => tkEl };
let tkQueued = null;
globalThis.requestAnimationFrame = (fn) => { tkQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* What each call to sfx BUILT, per call. The real sfx is still the one
   doing the work - this only brackets it - so the mute and the volume dial
   stay inside the measurement: a muted call comes back having constructed
   nothing, which is a different reading from a call that never happened. */
const tkCalls = [];
const tkRealSfx = sfx;
sfx = function(name, pitch){ const at = tkBuilt.length;
  const out = tkRealSfx.call(this, name, pitch);
  /* The pitch each call asked for, so "it does not climb" is a read fact
     rather than a promise: a tick that leant on the player would raise
     this from one second to the next (条件③). */
  tkCalls.push({ name: String(name), built: tkBuilt.length - at,
    pitch: (typeof pitch === 'number') ? pitch : null });
  return out };
/* `code` is not the key (C-1623). Space's code is 'Space'; sending ' '
   reaches nothing that gates on e.code, which is how the mash probe next
   door spent five thousand frames pressing a key no page was listening
   for. Harmless here today - the only key this one holds is ArrowLeft,
   whose code IS 'ArrowLeft' - and corrected so it stays that way. */
function tkPress(key){ tkKeys.forEach(fn => fn(probeKey(key))) }
function tkStep(){ if (!tkQueued) return false;
  const fn = tkQueued; tkQueued = null; tkTime += 50 / 3; fn(tkTime); return true }
tkStep(); tkStep();
if (MUTE_INPUT) { tkPress('m') }
tkPress(' ');
const tkHold = HOLD_INPUT;
const tkFrames = [];
for (let f = 0; f < FRAMES_INPUT; f++) {
  if (tkHold) { tkPress(tkHold) }
  const before = tkCalls.length;
  if (!tkStep()) break;
  const facts = roundClockFacts();
  tkFrames.push({ remain: facts.remain, left: facts.left, urgent: facts.urgent,
    due: facts.due, done: roundFacts().done, said: roundTickFacts().said,
    /* Only what this frame asked for, so "once a second" is a per-frame
       fact rather than a total that could have arrived all at once. */
    calls: tkCalls.slice(before) });
}
console.log(JSON.stringify({ frames: tkFrames, urgentAt: roundClockFacts().urgentAt,
  limit: roundClockFacts().limit, muted: !!MUTE_INPUT }));
"""


#: Does a mash carried through the buzzer erase the result? (C-1472)
#:
#: The page is driven for real: the round is started, a key or a tap is
#: repeated on every frame across the buzzer, and the count of
#: ``location.reload()`` calls is read frame by frame. The one thing this
#: has to be able to say is *when* the reload happened, because "the shield
#: works" and "restart is broken" produce the same total.
SHIELD_PROBE = KEY_EVENT_JS + """
const shNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : shNothing),
  apply: () => shNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false, addEventListener(){}, addListener(){} });
let shTime = 0;
globalThis.performance = { now: () => shTime };
const shKeys = [], shPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') shKeys.push(fn) };
globalThis.Image = function(){ return shNothing };
const shStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in shStore ? shStore[k] : null),
  setItem: (k, v) => { shStore[k] = String(v) }, removeItem: (k) => { delete shStore[k] } };
/* The whole measurement. A reload is the page being destroyed, so counting
   it is counting the result screens that never got read. */
let shReloads = 0;
globalThis.location = { reload: () => { shReloads++ } };
/* Recording, not swallowing: 「ここまで」 has to be on the screen for the
   shield to be protecting anything. */
const shText = [];
const shEl = { width: 720, height: 320, style: {}, textContent: '', attrs: {},
  addEventListener: (type, fn) => { if (type === 'pointerdown') shPointers.push(fn) },
  setAttribute(){}, getAttribute(){ return null }, blur(){},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({ fillText: (t) => { shText.push(String(t)) } }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : shNothing)),
    set: () => true }) };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => shEl, querySelector: () => null, getElementById: () => shEl };
let shQueued = null;
globalThis.requestAnimationFrame = (fn) => { shQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function shPress(){ shKeys.forEach(fn => fn({ key: 'r', code: 'KeyR',
  preventDefault(){}, stopImmediatePropagation(){} })) }
function shTap(){ shPointers.forEach(fn => fn({ pointerType: 'touch', pointerId: 1,
  clientX: 360, clientY: 160, preventDefault(){}, stopImmediatePropagation(){} })) }
function shPoke(){ if (MASH_INPUT === 'tap') { shTap() } else { shPress() } }
function shStep(){ if (!shQueued) return false;
  const fn = shQueued; shQueued = null; shTime += 50 / 3; fn(shTime); return true }
shStep(); shStep();
shKeys.forEach(fn => fn(probeKey(' ')));
/* Play to the buzzer without touching R, so the mash starts exactly where
   the item says it does - at the buzzer, not before it. */
let shBuzzerAt = null;
for (let f = 0; f < FRAMES_INPUT; f++) {
  if (!shStep()) break;
  if (roundFacts().done) { shBuzzerAt = f; break }
}
const shAtBuzzer = { reloads: shReloads, facts: roundFacts() };
/* Every frame of the mash, with the reload count as it stood: the frame a
   reload first appears on is the number that decides this. */
const shMash = [];
let shFirstReload = null;
for (let f = 0; f < MASH_FRAMES_INPUT; f++) {
  shPoke();
  if (shFirstReload === null && shReloads > 0) { shFirstReload = f }
  shMash.push({ frame: f, reloads: shReloads,
    shieldFrames: roundFacts().shieldFrames, shielded: roundFacts().shielded });
  if (!shStep()) break;
}
/* The other direction: after the mash stops, one press has to restart the
   way it always did. Nothing was queued, so this is a fresh press. */
const shBeforeLate = shReloads;
shPoke();
shStep();
console.log(JSON.stringify({
  buzzerAt: shBuzzerAt,
  atBuzzer: shAtBuzzer.reloads,
  /* Whether the template had ended on its own by the time the mash began.
     Without this, "the buzzer never fired" cannot be told apart from "the
     page stopped scheduling", and the scope claim rests on that difference. */
  endedByItself: !!shAtBuzzer.facts.ended,
  doneAtStop: !!shAtBuzzer.facts.done,
  mash: shMash,
  firstReloadAt: shFirstReload,
  reloadsAfterMash: shBeforeLate,
  reloadsAfterOneLatePress: shReloads,
  shield: roundFacts().shield,
  hold: roundFacts().hold,
  said: shText.slice(-40),
  running: shQueued !== null,
}));
"""


def shield_probe_source(
    script: str,
    *,
    frames: int = 4200,
    mash_frames: int = 60,
    mash: str = "key",
) -> str:
    """The page's own script, driven with a mash carried through the buzzer.

    ``mash`` is ``"key"`` or ``"tap"`` - both restart the round and both have
    to be shielded, and a probe that only ever pressed R would pass against a
    build that shielded the keyboard and left the canvas open.
    """

    # MASH_FRAMES_INPUT before FRAMES_INPUT: the shorter name is a substring
    # of the longer one, and replacing it first turns the other into
    # ``MASH_4200``. Caught by running the probe, not by reading it.
    return (
        SHIELD_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("MASH_FRAMES_INPUT", str(int(mash_frames)))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("MASH_INPUT", json.dumps(mash))
    )


def tick_probe_source(
    script: str,
    *,
    frames: int = 3900,
    hold: str = "",
    mute: bool = False,
    store: dict[str, str] | None = None,
) -> str:
    """The page's own script, wrapped so the last seconds can be listened to."""

    return (
        TICK_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("HOLD_INPUT", json.dumps(hold))
        .replace("MUTE_INPUT", "true" if mute else "false")
        .replace("STORE_INPUT", json.dumps(store or {}))
    )


def clock_probe_source(
    script: str,
    *,
    frames: int = 3900,
    reduced: bool = False,
    hold: str = "",
    gap_ms: int = 0,
    gap_at: int = 0,
) -> str:
    """The page's own script, wrapped so a whole go can be watched tick down.

    ``gap_ms`` inserts an absence of that many milliseconds before frame
    ``gap_at`` - the shape a hidden tab has when it comes back (C-1450).
    Left at 0 the run is exactly what it was before the option existed.
    """

    return (
        CLOCK_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("HOLD_INPUT", json.dumps(hold))
        .replace("GAP_MS_INPUT", str(int(gap_ms)))
        .replace("GAP_AT_INPUT", str(int(gap_at)))
    )


#: Does mindless mashing win? (C-1501)
#:
#: The masher presses one key every frame and steers not at all - the
#: cheapest possible input, and the one a difficulty label has to answer.
#: Two readings come back, both from driving the real page:
#:
#: * ``struck`` - how many times the SHARED damage sound fired after play
#:   began. ``sfx('hurt')`` is what every template plays when the player is
#:   hit, so this is one signal that needs no per-template knowledge.
#: * ``state`` - what the run ended as, so "never hit AND won" is separable
#:   from "never hit because it never finished".
#:
#: The prologue is excluded by counting only from the frame the template
#: first accepts input: kaiju roars with the same ``hurt`` sound on its
#: opening frame, and a probe that counted that would report a masher as
#: punished by the title card.
MASH_PROBE = KEY_EVENT_JS + """
const mNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : mNothing),
  apply: () => mNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false, addEventListener(){}, addListener(){} });
let mTime = 0;
globalThis.performance = { now: () => mTime };
function MContext(){ this.state='running'; this.currentTime=0; this.destination={};
  this.sampleRate=44100 }
MContext.prototype.createPeriodicWave = function(){ return { kind:'wave' } };
MContext.prototype.createOscillator = function(){
  return { type:'', setPeriodicWave(){},
    frequency:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} },
    connect(){}, start(){}, stop(){} } };
MContext.prototype.createBuffer = function(ch, len){
  return { getChannelData: () => new Float32Array(len) } };
MContext.prototype.createBufferSource = function(){
  return { buffer:null, start(){}, stop(){}, connect(){} } };
MContext.prototype.createBiquadFilter = function(){
  return { type:'', frequency:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} },
    connect(){} } };
MContext.prototype.createGain = function(){
  return { gain:{ setValueAtTime(){}, exponentialRampToValueAtTime(){}, value: 0 },
    connect(){} } };
globalThis.window = { AudioContext: MContext };
const mKeys = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') mKeys.push(fn) };
globalThis.Image = function(){ return mNothing };
const mStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in mStore ? mStore[k] : null),
  setItem: (k, v) => { mStore[k] = String(v) }, removeItem: (k) => { delete mStore[k] } };
globalThis.location = { reload: () => {} };
const mEl = { width: 720, height: 320, style: {}, textContent: '', attrs: {},
  addEventListener(){}, setAttribute(){}, getAttribute(){ return null }, blur(){},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => mNothing };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => mEl, querySelector: () => null, getElementById: () => mEl };
let mQueued = null;
globalThis.requestAnimationFrame = (fn) => { mQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
/* The shared damage sound, counted around the real sfx so the mute and the
   volume dial stay inside the measurement. */
let mStruck = 0, mCounting = false;
const mRealSfx = sfx;
sfx = function(name, pitch){
  if (mCounting && String(name) === 'hurt') { mStruck++ }
  return mRealSfx.call(this, name, pitch) };
/* Both halves of the event, because the ten pages do not agree on which
   one they read (C-1623): kaiju fires on `e.key===' '`, shooter, duel,
   puzzle and fishing on `e.code==='Space'`. Sending `code: ' '` - a code
   that does not exist - drove the first group and left the second
   untouched, so "one key every frame" was measured on a shooter that
   fired 0 shots in 5400 frames. */
function mPress(key){ mKeys.forEach(fn => fn(probeKey(key))) }
/* What "punished" is read off (C-1623). The shared damage SOUND is not a
   verdict: shooter plays sfx('hurt') when a FOE dies and does not play it
   when the ship does, so a run in which the player was killed came back
   as "unscathed", and duel's plays for whichever fighter was hit. The
   shared FAILURE BEAT is the one signal that means the player lost - it
   is what roundLost() already reads.
   The round clock rings it too, once, when the buzzer goes, and every
   unattended run reaches the buzzer. So only beats that land while the go
   is still being PLAYED are punishment; the buzzer's own is not. */
let mFails = 0, mBeaten = 0;
const mRealFail = failBeat;
failBeat = function(x, y){
  if (mCounting) { mFails++; if (!ROUND_DONE) { mBeaten++ } }
  return mRealFail.call(this, x, y) };
function mStep(){ if (!mQueued) return false;
  const fn = mQueued; mQueued = null; mTime += 50 / 3; fn(mTime); return true }
mStep(); mStep();
mPress(' ');
/* Only from here: a prologue that roars with the damage sound is not the
   player being hit (kaiju does exactly that on its first frame). */
for (let f = 0; f < WARMUP_INPUT; f++) { if (!mStep()) break }
mCounting = true;
/* A list, so "presses one key and never steers" can be compared against
   "presses the same key and also walks". A fix that punished standing
   still would be indistinguishable from one that punished playing at all
   if only the first could be driven. */
const mHold = HOLD_INPUT;
let mEndedAt = null;
for (let f = 0; f < FRAMES_INPUT; f++) {
  mHold.forEach(mPress);
  if (!mStep()) break;
  const facts = roundFacts();
  if (mEndedAt === null && (facts.done || facts.ended)) { mEndedAt = f }
}
const mEnd = roundFacts();
/* The instrument proving itself: the count has to be able to move. A
   run that reports "never struck" is only evidence if a real call to the
   shared damage sound would have been seen. */
const mBeforeSelf = mStruck, mBeatenFinal = mBeaten, mFailsBefore = mFails;
try { sfx('hurt') } catch (e) {}
const mSelfCheck = mStruck - mBeforeSelf;
/* Read AFTER the beaten count is banked: a run that ended on its own
   terms (racing reaches its goal) leaves ROUND_DONE false, so the proving
   call would otherwise land in the count it is proving. */
try { failBeat(0, 0) } catch (e) {}
const mFailCheck = mFails - mFailsBefore;
console.log(JSON.stringify({
  beaten: mBeatenFinal,
  failCheck: mFailCheck,
  fails: mFailsBefore,
  struck: mBeforeSelf,
  selfCheck: mSelfCheck,
  state: mEnd.state,
  reason: mEnd.reason,
  endedAt: mEndedAt,
  done: !!mEnd.done,
  ended: !!mEnd.ended,
  score: mEnd.score,
  live: mEnd.live,
  running: mQueued !== null,
}));
"""


def mash_probe_source(
    script: str,
    *,
    frames: int = 5400,
    warmup: int = 150,
    hold: str | Sequence[str] = " ",
) -> str:
    """The page's own script, driven by one key held down and nothing else.

    ``warmup`` frames are played before counting starts, so an opening
    that uses the shared damage sound as a roar is not counted as the
    player being hit. It is longer than kaiju's 90-frame prologue on
    purpose - the count has to start inside the fight, not on its edge.

    Two counts come back and they are not the same reading (C-1623).
    ``beaten`` is the shared FAILURE BEAT rung while the go was still
    being played, which is the one signal that means the player lost.
    ``struck`` is the shared damage SOUND, kept because it is worth
    seeing and never used as the verdict: it fires for a foe's death in
    the shooter and stays silent for the ship's own.
    """

    return (
        MASH_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("WARMUP_INPUT", str(int(warmup)))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace(
            "HOLD_INPUT",
            json.dumps([hold] if isinstance(hold, str) else list(hold)),
        )
    )
