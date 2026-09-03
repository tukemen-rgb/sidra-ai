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

#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``seedNow`` would break
#: only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "seedNow",
    "dailyOn",
    "dailyStamp",
    "dailySeed",
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
function seedNow(fallback){return dailyOn()?dailySeed():fallback}
"""


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
        .replace("DAILY_PLACEHOLDER", DAILY_PREAMBLE)
    )


__all__ = ["DAILY_PREAMBLE", "PREAMBLE_NAMES", "PROBE", "probe_source"]
