"""The best run, played back beside the current one.

§11 事実 1: racing your own ghost raises effort, enjoyment and
self-efficacy - measured at Bath, and two ghosts beat one. The personal
best already existed here (C-1106) but only as a number on a strip: there
was no way to *play with* the run that set it.

The mechanism is the smallest one that is honestly a ghost:

* **Indexed by progress, not by time.** A trail keyed to the frame count
  would drift out of step the moment the new run is faster. Keyed to the
  course position, the ghost is always "where you were at this point",
  which is the question the player is actually asking.
* **It cannot touch anything.** The ghost is drawn and nothing else - no
  collision, no score, no sound. A past run that could obstruct the
  present one would be a second car, not a memory.
* **It is banked only on a record**, through the same ``roundBank`` that
  already writes the best score, so the trail and the number it belongs
  to can never describe different runs.
* **It stays on the device**, in ``sidra.ghost.<template>``, like every
  other thing this page remembers.

Wired to the racing template first, as the item allows: its progress is a
single number along a course, which is the shape this needs. Templates
whose progress is a position in a room need a different trail, and that
is written down rather than half-built.

``marble`` is the second (C-1412), and it needed nothing new: z down the
corridor is the same shape as distance around a lap, so the same trail,
the same key and the same switch carry over. The only marble-specific
decision is where the past self is drawn - at the present marble's own
depth, so the two are compared where the player is looking, and under it,
so the present is never hidden by the past.

``platformer`` is the third (C-1330), and the "needs a second axis" note
that parked it resolves the same way the marble did: the course x is the
progress, the HEIGHT is the stored value, and the past self is drawn at
the present hero's own screen x - at the height the record run had here,
so "they were up on the ledge while I am in the pit" is read exactly
where the player is looking. Backtracking overwrites a bucket with the
later visit, which keeps the trail meaning "where you were, here, last
time" even on a course that can be walked both ways.
"""

from __future__ import annotations

import json

#: Templates whose progress is one number along a course, which is what a
#: progress-indexed trail needs. The others are listed with the reason
#: they are not here, so a later item starts from the fact rather than
#: from an empty function.
GHOST_TEMPLATES: tuple[str, ...] = ("racing", "marble", "platformer")

#: Why each of the others is not wired yet. A template with no progress
#: axis has nothing to index a trail by.
GHOST_UNWIRED: dict[str, str] = {
    "shooter": "the ship holds station; the course is the wave number, not a distance",
    "adventure": "progress is which room, not a position on a line",
    "kaiju": "the fight is a cycle count, not a course",
    "catch": "no progress axis at all: the basket is where you left it",
    "fishing": "no progress axis at all: the marker sweeps for ever",
    "puzzle": "the board is the state; a position would not describe it",
    "duel": "progress is the other side's health, which the ghost cannot re-run",
}

#: How far apart the samples are, in course units. Fine enough that the
#: ghost moves smoothly, coarse enough that a whole run is a couple of
#: kilobytes in a browser's storage.
GHOST_STEP = 12

#: Names the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "ghostOn",
    "ghostSample",
    "ghostAt",
    "ghostBank",
    "ghostForget",
    "ghostFacts",
    "ghostRunHash",
)

GHOST_PREAMBLE = """
/* --- the best run, played back beside this one (§11 事実 1) ----------- */
const GHOST_KEY='sidra.ghost.'+GHOST_NAME_TOKEN,GHOST_STEP=GHOST_STEP_TOKEN;
let GHOST_TRAIL=null,GHOST_RUN=[],GHOST_DRAWN=0,GHOST_SAVED=0,GHOST_LAST=null;
function ghostStore(){try{return (typeof localStorage!=='undefined')?localStorage:null}
  catch(e){return null}}
/* On by default: a past self that has to be switched on is a past self
   nobody meets. The panel can put it away (C-1113). */
function ghostOn(){try{return tuneFlag('ghost',true)}catch(e){return true}}
function ghostRead(){const s=ghostStore();if(!s)return null;
  try{const raw=s.getItem(GHOST_KEY);if(!raw)return null;
    const v=JSON.parse(raw);
    return (v&&Object.prototype.toString.call(v)==='[object Array]'&&v.length)?v:null}
  catch(e){return null}}
GHOST_TRAIL=ghostRead();
/* Indexed by where you are on the course, not by how long you have been
   playing: a faster run would slide out of step with a time-keyed trail,
   and the ghost would stop meaning anything. */
function ghostBucket(progress){return Math.max(0,Math.floor(progress/GHOST_STEP))}
function ghostSample(progress,x){const at=ghostBucket(progress);
  if(!isFinite(x))return;
  GHOST_RUN[at]=Math.round(x)}
/* Where you were, here, last time. Null before there is a last time - and
   the caller draws nothing rather than drawing a guess. */
function ghostAt(progress){
  if(!ghostOn()||!GHOST_TRAIL)return null;
  const v=GHOST_TRAIL[ghostBucket(progress)];
  if(typeof v!=='number'||!isFinite(v))return null;
  /* The bucket asked for and the value handed back, kept on the page.
     A judge that wants to know the ghost is where the last run was has
     to compare against *that* run; re-deriving the bucket out here would
     only prove the arithmetic agrees with itself (C-1412). */
  GHOST_DRAWN++;GHOST_LAST=[ghostBucket(progress),v];return v}
/* The demo's line is nobody's (C-1414). The attract run samples the same
   course buckets a player would, so without this a demo that got further
   than the player leaves its own positions in the tail of the trail that
   gets banked as theirs. */
function ghostForget(){GHOST_RUN=[];GHOST_DRAWN=0;GHOST_LAST=null}
/* Banked with the score it belongs to, through roundBank, so the trail and
   the number can never describe different runs. */
function ghostBank(record){if(!record)return false;
  const trail=[];for(let i=0;i<GHOST_RUN.length;i++){
    trail.push(typeof GHOST_RUN[i]==='number'?GHOST_RUN[i]:null)}
  while(trail.length&&trail[trail.length-1]===null){trail.pop()}
  if(!trail.length)return false;
  const s=ghostStore();
  try{if(s){s.setItem(GHOST_KEY,JSON.stringify(trail));GHOST_SAVED++}}catch(e){}
  return true}
/* This run's own path, as one number. "The ghost touches nothing" is a
   claim about the car, so the judge compares the car - a lap count is too
   coarse to notice a ghost that quietly drags it, which a deliberate
   break proved. */
function ghostRunHash(){let h=2166136261;
  for(let i=0;i<GHOST_RUN.length;i++){
    const s=String(i)+':'+String(GHOST_RUN[i]);
    for(let j=0;j<s.length;j++){h^=s.charCodeAt(j);h=Math.imul(h,16777619)>>>0}}
  return h}
function ghostFacts(){return {on:ghostOn(),had:GHOST_TRAIL!==null,
  drawn:GHOST_DRAWN,saved:GHOST_SAVED,
  last:GHOST_LAST?GHOST_LAST.slice():null,
  samples:GHOST_RUN.filter(function(v){return typeof v==='number'}).length,
  runHash:ghostRunHash(),
  stored:(ghostRead()||[]).length}}
/* --- end ghost --- */
"""


def preamble_for(template: str) -> str:
    """The ghost, told which page it belongs to."""

    return GHOST_PREAMBLE.replace("GHOST_NAME_TOKEN", json.dumps(template)).replace(
        "GHOST_STEP_TOKEN", str(GHOST_STEP)
    )


__all__ = [
    "GHOST_PREAMBLE",
    "GHOST_STEP",
    "GHOST_TEMPLATES",
    "GHOST_UNWIRED",
    "PREAMBLE_NAMES",
    "preamble_for",
]
