"""Three losses in a row, and the game steps toward you once.

§11 事実 2: a player who keeps failing stops playing, and the difficulty
dial is no help to them because reaching for it means admitting to a
setting. §11 事実 3 is the warning attached: hidden dynamic difficulty
breeds two problems at once - players who suspect it stop trusting their
wins, and players who confirm it farm it by losing on purpose.

So this is deliberately the smallest version that is still worth having,
and the least secretive:

* **One step, toward the easy end of the author's own ladder.** Not a
  percentage and not a slide: the value it moves to is a value the author
  shipped. "Easier" is the direction of the ladder's ``easy`` entry, not
  "smaller" - the catch template's axis is the *interval* between drops,
  where larger is gentler, and a rule about numbers rather than about the
  ladder would have made that one harder.
* **Only at a boundary.** The speed is read once when the page loads, so
  nothing can shift under a player mid-round.
* **It says so.** The page prints which step it is on, next to the panel.
  A player who is being helped can see that they are.
* **A hand-set value always wins.** If the person moved the slider, that
  is their decision, and this does not touch it.

A win clears the streak, so the help lasts exactly as long as the trouble.

Known limit, written down rather than hidden: the eased value applies from
the next time the page loads. Templates that restart in place (duel,
racing, shooter) keep the speed they started with until then. Moving the
read into the frame loop would let a value change under a player, which
is the thing the boundary rule exists to prevent - so the fix, if it is
wanted, is for those templates to re-read on reset, and that is a
template change rather than a rule change.
"""

from __future__ import annotations

import json

#: How many losses in a row before the game steps toward the player. Three
#: is §11's number: two is noise, and by four the player has left.
ADAPT_AFTER = 3

#: Names the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = (
    "adaptStreak",
    "adaptManual",
    "adaptSpeed",
    "adaptRecord",
    "adaptEasing",
    "adaptFacts",
)

ADAPT_PREAMBLE = """
/* --- three losses in a row, and one step toward you (§11 事実 2-3) ---- */
const ADAPT_KEY='sidra.streak.'+ADAPT_NAME_TOKEN;
/* The author's own three speeds, easy first. Stepping toward index 0 is
   what "easier" means here - which is why the catch template, whose axis
   is the interval between drops and therefore larger-is-gentler, needs no
   special case. */
const ADAPT_STEPS=ADAPT_STEPS_TOKEN,ADAPT_AFTER=ADAPT_AFTER_TOKEN;
let ADAPT_EASED=false;
function adaptStore(){try{return (typeof localStorage!=='undefined')?localStorage:null}
  catch(e){return null}}
function adaptStreak(){const s=adaptStore();if(!s)return 0;
  try{const v=Number(s.getItem(ADAPT_KEY));return (isFinite(v)&&v>0)?Math.floor(v):0}
  catch(e){return 0}}
/* A hand-set value is a decision. This never argues with one. */
function adaptManual(){try{return tuneStored('speed')}catch(e){return false}}
function adaptSpeed(v){ADAPT_EASED=false;
  if(adaptManual())return v;
  if(adaptStreak()<ADAPT_AFTER)return v;
  if(!ADAPT_STEPS.length)return v;
  let at=0,best=Infinity;
  for(let i=0;i<ADAPT_STEPS.length;i++){const d=Math.abs(ADAPT_STEPS[i]-v);
    if(d<best){best=d;at=i}}
  if(at<=0)return v;
  ADAPT_EASED=true;return ADAPT_STEPS[at-1]}
/* Recorded at the boundary, from the shared failure beat: a round that
   fired one was lost, and C-1105's own judge is what keeps that true. */
function adaptRecord(lost){const s=adaptStore();
  const next=lost?adaptStreak()+1:0;
  try{if(s)s.setItem(ADAPT_KEY,String(next))}catch(e){}
  return next}
/* Whether this load is being helped. Computed rather than remembered:
   the line below is written before the template body calls adaptSpeed, so
   a flag set in there would still be false and the page would say 標準
   while easing. Found by the judge, which is what it is for. */
function adaptEasing(){return !adaptManual()&&adaptStreak()>=ADAPT_AFTER&&ADAPT_STEPS.length>1}
/* Said out loud, next to the panel. A player being helped can see it. */
function adaptPanel(){
  if(typeof document==='undefined'||!document.createElement)return null;
  const host=(document.querySelector&&document.querySelector('main'))||document.body;
  if(!host||!host.appendChild)return null;
  const p=document.createElement('p');p.id='adapt';
  p.style.cssText='margin:8px 0 0;font-size:13px;opacity:0.8';
  p.textContent=adaptManual()?'今の調整: 手動（自分で設定した値）'
    :(adaptEasing()?('今の調整: 1 段やさしく（'+adaptStreak()+' 連敗のため。勝てば戻ります）')
    :'今の調整: 標準');
  host.appendChild(p);return p}
function adaptFacts(){return {streak:adaptStreak(),eased:ADAPT_EASED,easing:adaptEasing(),
  manual:adaptManual(),after:ADAPT_AFTER,steps:ADAPT_STEPS}}
if(typeof document!=='undefined'&&document.addEventListener&&document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',adaptPanel)}else{adaptPanel()}
/* --- end adapt --- */
"""


def preamble_for(template: str, speeds: tuple[float, ...]) -> str:
    """The rule, told this template's own ladder (easy first)."""

    return (
        ADAPT_PREAMBLE.replace("ADAPT_NAME_TOKEN", json.dumps(template))
        .replace("ADAPT_STEPS_TOKEN", json.dumps(list(speeds)))
        .replace("ADAPT_AFTER_TOKEN", str(ADAPT_AFTER))
    )


__all__ = ["ADAPT_AFTER", "ADAPT_PREAMBLE", "PREAMBLE_NAMES", "preamble_for"]
