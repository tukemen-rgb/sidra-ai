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
    "catch": ("score", "受け"),
    # Damage dealt, not health kept: a duel lost 3-2 was closer than one
    # lost 3-0, and only the first of those is worth chasing.
    "duel": ("3-e.hp", "与ダメージ"),
    "fishing": ("score", "釣果"),
    "kaiju": ("cycles", "頭部への一撃"),
    "marble": ("gates", "通過ゲート"),
    "platformer": ("me.gems", "宝石"),
    "puzzle": ("score", "得点"),
    "racing": ("times.length", "完了ラップ"),
    "shooter": ("score", "撃墜"),
}

#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``roundFacts`` would
#: break only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "roundLive",
    "roundEnded",
    "roundFacts",
    "roundScore",
    "roundBest",
    "ROUND_DONE",
    "ROUND_LIMIT_MS",
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
function roundTick(t){
  const now=(typeof t==='number'&&isFinite(t))?t:ROUND_MS+16;
  if(ROUND_T0===null){ROUND_T0=now}
  ROUND_MS=now-ROUND_T0;
  /* The template finished on its own: its screen is the break, and the
     clock has nothing to add. Reset so a restart gets a full go. */
  if(roundEnded()){ROUND_T0=now;ROUND_MS=0;ROUND_REASON='template';return}
  /* A template that restarts in place (kaiju's tap, the duel's R) begins a
     round the bank has already been closed for. Without this the second
     go's strip - and the line C-1110 copies - would still be reporting the
     first one's score. */
  if(ROUND_BANKED&&!ROUND_DONE){ROUND_BANKED=false;ROUND_FINAL=null;ROUND_RECORD=false}
  /* Once the clock has fired, only an explicit restart clears it. An
     earlier version cleared it as soon as the template looked "live"
     again - but the clock fires precisely when the template has *not*
     finished, so ``state`` was still live and the banner lasted a single
     frame. Found by driving the page rather than by reading it. */
  if(ROUND_DONE){return}
  if(ROUND_MS>=ROUND_LIMIT_MS){ROUND_DONE=true;ROUND_REASON='time';
    /* Running out of time without finishing is a failed round, and it is
       the only failure the four templates with no losing state have. The
       beat is the shared one (C-1105), not a second thing that looks like
       it. */
    try{failBeat(RCV?RCV.width/2:0,RCV?RCV.height/2:0)}catch(e){}}}
function drawRoundEnd(){if(!RCV)return;
  const c=RCV.getContext('2d'),W=RCV.width,H=RCV.height;
  c.save();c.fillStyle='#05070fcc';c.fillRect(0,H/2-52,W,104);
  c.fillStyle='#dfe7f5';c.textAlign='center';
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
/* Banked once per round, on the first frame it is over: reading the score
   every frame afterwards would keep overwriting the best with whatever the
   frozen page still holds. Kept on this device only - no URL, nothing
   sent, the same boundary the tuning panel and the index sit inside. */
function roundBank(){if(ROUND_BANKED)return;ROUND_BANKED=true;
  ROUND_FINAL=roundScore();ROUND_BEST=roundBestRead();
  if(ROUND_FINAL===null)return;
  if(ROUND_BEST===null||ROUND_FINAL>ROUND_BEST){ROUND_RECORD=true;
    roundBestWrite(ROUND_FINAL);ROUND_BEST=ROUND_FINAL}
  /* The same number, banked a second way: the best is this round against
     the last one, the total is every round there has ever been (C-1109).
     Both stay on this device. */
  try{skinBank(ROUND_FINAL)}catch(e){}
  /* The trail that set this record, kept with the number (C-1401). */
  try{ghostBank(ROUND_RECORD)}catch(e){}
  /* Won or lost, for the run after this one (C-1402). A round that
     fired the shared failure beat is a round that was lost. */
  try{adaptRecord(failBeats()>0)}catch(e){}}
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
  c.save();c.fillStyle='#05070fe6';c.fillRect(0,H-52,W,52);
  c.fillStyle='#dfe7f5';c.textAlign='center';
  c.font='13px ui-monospace,monospace';
  let left='';
  if(ROUND_FINAL!==null){
    left=ROUND_LABEL+' '+ROUND_FINAL;
    if(ROUND_RECORD){left+=' / 自己ベスト更新'}
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
  /* A colour that just opened is the reason to start the next round, so it
     is said on the screen that asks for one - and only when it happened. */
  let news=null;try{news=skinNews()}catch(e){}
  if(news){c.fillStyle='#05070fe6';c.fillRect(0,H-82,W,30);
    c.fillStyle=TUNE_ACCENT;
    c.fillText('新しい見た目「'+news+'」が開きました',W/2,H-62)}
  c.textAlign='left';c.restore()}
function roundFacts(){return {ms:ROUND_MS,done:ROUND_DONE,reason:ROUND_REASON,
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
    getContext: () => new Proxy({ fillText: (t) => { roundText.push(String(t)) } }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : roundNothing)),
      set: () => true }) }) };
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
for (let f = 0; f < FRAMES_INPUT; f++) {
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
) -> str:
    """The page's own script, started once and then left alone.

    ``warmup`` is how many frames sit on the title screen before the
    single press. Those frames have to cost the round nothing.
    """

    payload = {key: json.dumps(value, ensure_ascii=False) for key, value in (stored or {}).items()}
    return (
        PROBE.replace("FRAMES_INPUT", str(int(frames)))
        .replace("WARMUP_INPUT", str(int(warmup)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("STAMP_INPUT", stamp)
        .replace("STORED_INPUT", json.dumps(payload, ensure_ascii=False))
        .replace("SCRIPT_PLACEHOLDER", script)
    )


def preamble_for(template: str) -> str:
    """The clock and the result strip, told about one template."""

    expression, label = ROUND_SCORE.get(template, ("null", "得点"))
    return (
        ROUND_PREAMBLE.replace(
            "ROUND_LIVE_TOKEN", json.dumps(list(ROUND_LIVE.get(template, ())))
        )
        .replace("ROUND_LIMIT_TOKEN", str(ROUND_SECONDS * 1000))
        .replace("ROUND_NAME_TOKEN", json.dumps(template))
        .replace("ROUND_LABEL_TOKEN", json.dumps(label, ensure_ascii=False))
        .replace("ROUND_SCORE_TOKEN", expression)
    )


__all__ = [
    "PREAMBLE_NAMES",
    "PROBE",
    "ROUND_LIVE",
    "ROUND_SCORE",
    "ROUND_PREAMBLE",
    "ROUND_SECONDS",
    "live_gaps",
    "preamble_for",
    "probe_source",
    "states_in",
]
