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

from sidra_ai.creation.juice import HAPTIC_ROUND

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
    "kaiju": ("fight",),
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
    "roundScore",
    "roundBest",
    "ROUND_DONE",
    "ROUND_LIMIT_MS",
    "roundRemainMs",
    "roundLeft",
    "roundClockDue",
    "roundClockFacts",
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
function drawRoundEnd(){if(!RCV)return;
  const c=RCV.getContext('2d'),W=RCV.width,H=RCV.height;
  c.save();c.fillStyle='SCRIM_TOKEN'+'cc';c.fillRect(0,H/2-52,W,104);
  c.fillStyle='INK_TOKEN';c.textAlign='center';
  c.font='22px ui-monospace,monospace';c.fillText('ここまで',W/2,H/2-10);
  c.font='13px ui-monospace,monospace';
  c.fillText('R / タップでもう一度',W/2,H/2+22);
  c.textAlign='left';c.restore()}
/* The clock only ever fires over a game that had *not* finished, so there
   is no end screen to preserve: re-running the page is the whole restart,
   and it is the same one the tuning panel uses (C-1113). A template that
   ended on its own never gets here - its own R still owns that. */
function roundRestart(){if(!ROUND_DONE)return;
  try{if(typeof location!=='undefined'&&location&&typeof location.reload==='function'){
    location.reload()}}catch(e){}}
addEventListener('keydown',function(e){
  if(ROUND_DONE&&(e.key==='r'||e.key==='R')){roundRestart()}});
if(RCV){RCV.addEventListener('pointerdown',function(){if(ROUND_DONE){roundRestart()}})}
/* Outermost wrapper, installed after the pad: the banner has to be the last
   thing drawn, and holding the frame must not stop the loop. */
const ROUND_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return ROUND_RAF(function tick(t){
    roundTick(t);
    if(ROUND_DONE){drawRoundEnd();drawResultStrip();ROUND_RAF(tick);return}
    fn(t);
    /* Over the template's own frame, so the badge is not painted under the
       game (C-1417). It draws nothing at all until the last ten seconds. */
    drawRoundClock();
    /* The template drew its own ending; the strip goes on top of it. */
    if(roundEnded()){drawResultStrip()}})};
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
    if(ROUND_RECORD){left+=' / 自己ベスト更新'}
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
  try{if(dailyBoard()){mark='今日の挑戦 '+dailyStamp()+'   '}}catch(e){}
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
  let news=null;try{news=skinNews()}catch(e){}
  if(news){c.fillStyle='SCRIM_TOKEN'+'e6';c.fillRect(0,H-82,W,30);
    c.fillStyle=TUNE_ACCENT;
    c.fillText('新しい見た目「'+news+'」が開きました',W/2,H-62)}
  c.textAlign='left';c.restore()}
function roundFacts(){return {ms:ROUND_MS,done:ROUND_DONE,reason:ROUND_REASON,
  tie:roundTieFacts(),
  ended:roundEnded(),limit:ROUND_LIMIT_MS,
  score:ROUND_FINAL,best:ROUND_BEST,record:ROUND_RECORD,
  live:roundScore(),
  seed:(typeof SEED==='undefined')?null:SEED,
  daily:(function(){try{return dailyOn()}catch(e){return null}})(),
  stamp:(function(){try{return dailyStamp()}catch(e){return null}})(),
  state:(typeof state==='undefined')?null:state}}
"""


#: Runs a generated page for longer than the bound, pressing start once and
#: nothing after that. "A go ends" is a claim about a page left alone, so
#: the probe leaves it alone.
PROBE = """
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
const press = { key: ' ', code: 'Space',
  preventDefault(){}, stopImmediatePropagation(){} };
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
    "PREAMBLE_NAMES",
    "PROBE",
    "ROUND_LIVE",
    "ROUND_SCORE",
    "ROUND_TIE",
    "ROUND_PREAMBLE",
    "ROUND_SECONDS",
    "live_gaps",
    "preamble_for",
    "probe_source",
    "states_in",
]


#: Runs a generated page for a whole go and writes down, frame by frame,
#: whether the countdown said it was due and what it actually painted. Both
#: halves are needed: "due" is the page's own opinion and the painted text
#: is what a player sees, and C-1415's break table has an example of those
#: two coming apart (the condition decided correctly, the element never
#: touched).
CLOCK_PROBE = """
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
clkKeys.forEach(fn => fn({ key: ' ', code: 'Space',
  preventDefault(){}, stopImmediatePropagation(){} }));
const seen = [];
const clkHold = HOLD_INPUT;
for (let f = 0; f < FRAMES_INPUT; f++) {
  /* Some templates end on their own long before the buzzer when nobody
     touches them - a duel both sides refuse to fight is over in seconds.
     Holding a key keeps the go alive far enough in to reach the clock. */
  if (clkHold) { clkKeys.forEach(fn => fn({ key: clkHold, code: clkHold,
    preventDefault(){}, stopImmediatePropagation(){} })) }
  const painted = clkStep();
  if (painted === null) break;
  const facts = roundClockFacts();
  seen.push({ ms: facts.remain, due: facts.due, left: facts.left,
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


def clock_probe_source(
    script: str, *, frames: int = 3900, reduced: bool = False, hold: str = ""
) -> str:
    """The page's own script, wrapped so a whole go can be watched tick down."""

    return (
        CLOCK_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("HOLD_INPUT", json.dumps(hold))
    )
