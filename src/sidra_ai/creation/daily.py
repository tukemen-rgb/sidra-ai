"""A layout everyone gets today, without anyone talking to anyone.

§8 事実 4 and 7 of the play notes: what people come back for is a shared
attempt - the same board, the same day, "how did you do on today's one".
The obvious way to build that is a server handing out a puzzle, and the
obvious way is not available here: this project's whole shape is a page
that runs from a file and talks to nothing.

The way out is that a date is already shared. Every device knows what day
it is, so a seed derived from the date is a seed everyone derives the same
way, and the coordination cost is zero. Nothing is fetched and nothing is
sent - the page hashes ``YYYY-MM-DD`` and that is the whole mechanism.

Three things this deliberately is not:

* **Not the default.** The request-derived seed is what makes a generated
  game *that person's* game, and C-1112's revisions rebuild from the same
  request expecting the same world. The daily seed is a switch in the
  panel, off unless someone turns it on.
* **Not a clock.** The date is read once, at load. A page left open past
  midnight keeps the board it started - changing the world under a player
  mid-round would be a bug wearing a feature's clothes.
* **Not a leaderboard.** Everyone gets the same layout; nobody learns
  anyone else's score. The best stays in this browser, as C-1106 left it.
"""

from __future__ import annotations

import json

#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``seedNow`` would break
#: only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "dailyBoard",
    "seedNow",
    "dailyOn",
    "dailyStamp",
    "dailySeed",
    "dailyDay",
    "dailyStreak",
    "dailyStreakBank",
    "dailyStreakFacts",
)

DAILY_PREAMBLE = """
/* --- today's challenge: a seed a date decides (§8 事実 4・7) ---------- */
/* Read once, at load. A page left open past midnight keeps the board it
   started on; swapping the world under a player would be a bug. */
const DAILY_STAMP=(function(){try{const d=new Date();
  const p=function(n){return (n<10?'0':'')+n};
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())}
  catch(e){return ''}})();
function dailyStamp(){return DAILY_STAMP}
/* FNV-1a over the stamp. Any hash would do; what matters is that it is
   computed here, from a string every device already has, so "the same
   board as everyone else" costs no request. */
function dailySeed(){if(!DAILY_STAMP)return 0;
  let h=2166136261;
  for(let i=0;i<DAILY_STAMP.length;i++){h^=DAILY_STAMP.charCodeAt(i);
    h=Math.imul(h,16777619)>>>0}
  return h>>>0}
/* Off unless the panel says otherwise: the request-derived seed is what
   makes a generated game that person's game, and a revision rebuilt from
   the same request expects the same world back. */
function dailyOn(){try{return tuneFlag('daily',false)}catch(e){return false}}
/* Whether *this* page's board is the shared one. Two templates lay their
   board out with Math.random and have no SEED at all, so for them the
   switch can be on and the board still is not everybody's - and saying
   「今日の挑戦」 over it would be a false claim, in a line people paste.
   Found by C-1118's sweep; C-1107's judge only ever drove the adventure. */
function dailyBoard(){try{return dailyOn()&&typeof SEED!=='undefined'}
  catch(e){return false}}
function seedNow(fallback){return dailyOn()?dailySeed():fallback}
/* --- how many days running (§8 事実 4, C-1442) ------------------------ */
/* The switch says "everyone gets this board today"; this says how many
   todays in a row you have taken it. That is the only number here that is
   about coming back rather than about a round.
   It is NOT adapt.py's streak - that one counts losses in a row and a win
   clears it, which is a rescue and not a habit. Different key, different
   question.
   The day is the stamp read at load, so a page open past midnight keeps
   the day it started, exactly as the board does. */
const DAILY_STREAK_KEY='sidra.daily.'+DAILY_NAME_TOKEN;
/* Whole days since the epoch, from the stamp rather than from a Date: the
   two stamps being compared were both written by the same local reading,
   so counting them as UTC midnights cannot drift between them. */
function dailyDay(stamp){try{
  const p=String(stamp||'').split('-').map(Number);
  if(p.length!==3||p.some(function(n){return !isFinite(n)}))return null;
  return Math.floor(Date.UTC(p[0],p[1]-1,p[2])/86400000)}catch(e){return null}}
function dailyStreakRead(){try{
  const raw=localStorage.getItem(DAILY_STREAK_KEY);if(!raw)return null;
  const v=JSON.parse(raw);
  if(!v||typeof v.day!=='number'||typeof v.n!=='number')return null;
  return v}catch(e){return null}}
/* Counted once per day, when a round somebody actually played has ended on
   a board that really is everybody's. dailyBoard() rather than dailyOn():
   two templates lay their board out with Math.random and have no shared
   board to have taken, and C-1118 already established that claiming
   今日の over one of those is a false claim. */
function dailyStreakBank(){try{
  if(!dailyBoard())return;
  const day=dailyDay(DAILY_STAMP);if(day===null)return;
  const was=dailyStreakRead();
  if(was&&was.day===day)return;
  /* Yesterday carries; anything else starts again. No grace day: a gap
     that still read "5 日目" would be a number that had stopped meaning
     what it says (§9). */
  const n=(was&&was.day===day-1)?was.n+1:1;
  localStorage.setItem(DAILY_STREAK_KEY,JSON.stringify({day:day,n:n}))}
  catch(e){}}
/* What to show today, and only for today: a count banked yesterday is
   yesterday's, so an unplayed today reads 0 rather than carrying. */
function dailyStreak(){const v=dailyStreakRead(),day=dailyDay(DAILY_STAMP);
  return (v&&day!==null&&v.day===day)?v.n:0}
function dailyStreakFacts(){return {key:DAILY_STREAK_KEY,day:dailyDay(DAILY_STAMP),
  stored:dailyStreakRead(),shown:dailyStreak(),board:dailyBoard()}}
"""


def preamble_for(template: str) -> str:
    """The daily lines, told which game's streak they are keeping.

    ``ROUND_NAME_TOKEN`` is substituted by round.py over its own preamble
    only, so borrowing that name here would have reached the page as a
    bare identifier and thrown on load. Each preamble fills its own
    tokens, which is what share.py already does.
    """

    return DAILY_PREAMBLE.replace("DAILY_NAME_TOKEN", json.dumps(template))


#: Runs the preamble alone with the clock pinned, and prints what it made
#: of the date. Two dates and two runs of the same date is the whole claim:
#: same day, same seed; next day, a different one.
PROBE = """
globalThis.tuneFlag = (key, fallback) => (key === 'daily' ? DAILY_INPUT : fallback);
class FixedDate {
  constructor(){ return FixedDate.parse() }
  static parse(){ const [y, m, d] = 'STAMP_INPUT'.split('-').map(Number);
    return { getFullYear: () => y, getMonth: () => m - 1, getDate: () => d } }
}
globalThis.Date = FixedDate;
DAILY_PLACEHOLDER
console.log(JSON.stringify({
  stamp: dailyStamp(), on: dailyOn(),
  seed: seedNow(123456), daily: dailySeed(), fallback: 123456,
}));
"""


def probe_source(*, stamp: str, on: bool) -> str:
    """The preamble with the date and the switch pinned, ready for node."""

    return (
        PROBE.replace("STAMP_INPUT", stamp)
        .replace("DAILY_INPUT", "true" if on else "false")
        .replace("DAILY_PLACEHOLDER", preamble_for("probe"))
    )


#: A whole page, on a day of your choosing, played to the end.
#:
#: The streak is a claim about days, and a day is a page load - the stamp
#: is read once and never again, by design. So a run of days is a run of
#: PROCESSES, with only the store carried between them, exactly as C-1432
#: had to do for the row of runs (one round is one page). Anything that
#: pretended otherwise would be measuring a page that does not exist.
STREAK_PROBE = """
const sNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : sNothing),
  apply: () => sNothing, set: () => true });
const sKeys = [];
globalThis.matchMedia = () => ({ matches: false });
let sClock = 0;
globalThis.performance = { now: () => sClock };
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') sKeys.push(fn) };
globalThis.Image = function(){ return sNothing };
/* The day, pinned. Only the three getters the preamble uses. */
class FixedDate {
  constructor(){ return FixedDate.parse() }
  static parse(){ const [y, m, d] = 'STAMP_INPUT'.split('-').map(Number);
    return { getFullYear: () => y, getMonth: () => m - 1, getDate: () => d } }
}
FixedDate.UTC = Date.UTC;
FixedDate.now = () => 0;
globalThis.Date = FixedDate;
/* Whatever yesterday's load left behind, and it keeps what today writes. */
const sStore = STORE_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in sStore ? sStore[k] : null),
  setItem: (k, v) => { sStore[k] = String(v) },
  removeItem: (k) => { delete sStore[k] } };
const sDrawn = [];
const sCtx = new Proxy({ fillText: (t) => { sDrawn.push(String(t)) } },
  { get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : sNothing)),
    set: () => true });
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => sNothing, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => sCtx }) };
globalThis.location = { reload: () => {} };
let sQueued = null;
globalThis.requestAnimationFrame = (fn) => { sQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function sKey(k){ const e = { key: k, code: k === ' ' ? 'Space' : k,
  preventDefault(){}, stopImmediatePropagation(){} };
  sKeys.forEach(fn => fn(e)) }
function sStep(n, hold){ for (let i = 0; i < n && sQueued; i++) {
  if (hold) { sKey(hold) }
  const fn = sQueued; sQueued = null; sClock += 250; fn(sClock) } }
const before = dailyStreakFacts();
if (PLAY_INPUT) {
  sKey(' ');
  sStep(2, null);
  /* The clock ends a round too (C-1506). Asking only ``roundEnded()`` was
     dead code on every template - fishing and catch have no end state, and
     the rest are frozen live by the buzzer before they reach theirs - so
     this loop always ran its full guard. */
  let guard = 0;
  while (guard++ < 4000) {
    sStep(1, HOLD_INPUT);
    let done = false;
    try { done = roundEnded() || ROUND_DONE } catch (e) { done = false }
    if (done) break;
  }
}
/* The strip is what banks the round, so let it draw - and it waits out the
   ending's quiet beat (``ROUND_HOLD``, 45 frames) first. Six steps used to
   be enough only because the loop above overran and spent the beat by
   accident (C-1506). */
sDrawn.length = 0;
sStep(60, null);
console.log(JSON.stringify({
  stamp: dailyStamp(), on: dailyOn(), board: dailyBoard(),
  before: before, after: dailyStreakFacts(),
  touched: (function(){ try { return roundTouched() } catch (e) { return null } })(),
  said: sDrawn.filter(t => t.indexOf('今日の挑戦') === 0),
  store: sStore,
}));
"""


def streak_probe_source(
    script: str,
    *,
    stamp: str,
    store: dict[str, str] | None = None,
    play: bool = True,
    hold: str | None = "ArrowRight",
) -> str:
    """One day: the page loaded on ``stamp`` with ``store`` behind it."""

    return (
        STREAK_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("STAMP_INPUT", stamp)
        .replace("STORE_INPUT", json.dumps(store or {}, ensure_ascii=False))
        .replace("PLAY_INPUT", "true" if play else "false")
        .replace("HOLD_INPUT", json.dumps(hold))
    )


__all__ = [
    "DAILY_PREAMBLE",
    "PREAMBLE_NAMES",
    "PROBE",
    "STREAK_PROBE",
    "preamble_for",
    "probe_source",
    "streak_probe_source",
]
