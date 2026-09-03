"""The first mechanic that two templates run out of the same code.

§9 学び (3) is a warning about the N-templates approach: nine games is
nine games, and the tenth costs as much as the first. The way out is
supposed to be parts - movement, collision, scoring, enemy behaviour as
pieces that combine into genres nobody wrote by hand.

Before designing that, C-1114 measured what the nine templates actually
share today, and the answer is worth writing down because it is not the
answer the plan assumed:

* **27** identical non-trivial lines across ~1000 lines of template body.
* The most-shared lines are *infrastructure*, not mechanics: the canvas
  handle (9/9), the seeded ``rand`` (7/9), a font and colour setup (7/9).
* Of the four mechanics the plan names, exactly one is duplicated in a
  form that could be lifted as-is: **steering along x with a clamp**,
  written out four separate times (kaiju, racing, shooter, platformer),
  differing only in the key spellings, the speed and the margin.

And one finding that decides the shape of everything after this:
``catch`` works in normalised 0..1 coordinates while ``shooter`` works in
pixels; ``catch`` and ``fishing`` have no ``state``/``reset`` at all while
the other seven do. **The templates do not share mechanics because they do
not share a coordinate contract or an entity contract**, so "combine the
parts" is not extraction work - it is contract work that has to come
first. Pretending otherwise would produce a parts library only the two
templates it was extracted from could use.

So this module is deliberately one part, wired to two templates, as the
proof that the seam is in the right place: a part takes an actor and the
field it moves in, reads input through the page rather than through a
template's private key map, and returns the value it changed. Nothing
about a part knows which game it is in.
"""

from __future__ import annotations

#: What the part introduces, held to by a test like the other preambles'.
PREAMBLE_NAMES: tuple[str, ...] = (
    "partsHeld",
    "partsSteerX",
    "partsFacts",
)

#: The templates driving a mechanic through the shared part. Two, on
#: purpose: the PoC is whether the seam holds, not how many callers can be
#: converted in an afternoon. The other two that steer (shooter,
#: platformer) are left alone so the "before" is still in the tree to
#: compare against.
WIRED: tuple[str, ...] = ("kaiju", "racing")

#: The ones that steer but are not wired yet, and why each is more than a
#: substitution. Written down so the next person does not rediscover it.
UNWIRED: dict[str, str] = {
    "shooter": "also accepts A/D, so wiring it would change what keys do",
    "platformer": "clamps against the level width, not the canvas",
}

PARTS_PREAMBLE = """
/* --- mechanics parts: one shared contract, two callers (C-1114) ------- */
/* A part reads input through the page, never through a template's own key
   map: a template that kept its keys private could not be recombined with
   anything. Registered without capture, so the start gate still swallows
   the press that opens the game. */
const PARTS_KEYS={};
addEventListener('keydown',function(e){PARTS_KEYS[String(e.key).toLowerCase()]=true});
addEventListener('keyup',function(e){PARTS_KEYS[String(e.key).toLowerCase()]=false});
function partsHeld(names){for(let i=0;i<names.length;i++){
  if(PARTS_KEYS[String(names[i]).toLowerCase()])return true}
  return false}
let PARTS_MOVES=0;
/* 移動: steer along x, clamped to a field. Four templates had written this
   out; the differences between them were the key spellings, the speed and
   the margin - which is to say, the arguments. The actor is mutated and
   its new x returned, so a caller can use either. */
function partsSteerX(actor,speed,lo,hi,left,right){
  const back=left||['ArrowLeft'],fwd=right||['ArrowRight'];
  if(partsHeld(back)){actor.x=Math.max(lo,actor.x-speed);PARTS_MOVES++}
  if(partsHeld(fwd)){actor.x=Math.min(hi,actor.x+speed);PARTS_MOVES++}
  return actor.x}
/* What the judge reads back: that the part is the thing that moved the
   actor, rather than a template's own copy of the same three lines. */
function partsFacts(){return {moves:PARTS_MOVES,
  keys:Object.keys(PARTS_KEYS).filter(function(k){return PARTS_KEYS[k]})}}
/* --- end mechanics parts --- */
"""


#: Where the seam has to go before a fifth caller is worth converting, in
#: the order the work has to happen. Not a plan for this cycle - the point
#: of the measurement above is that these are prerequisites, and writing
#: them down is the deliverable C-1114 asked for.
CONTRACT_GAPS: tuple[tuple[str, str], ...] = (
    (
        "coordinates",
        "catch and fishing place things in 0..1 of the canvas; the other "
        "seven use pixels. A part that moves or overlaps anything has to be "
        "told which, or every caller converts at the boundary.",
    ),
    (
        "entities",
        "there is no shared shape for a thing in the world. foes carry "
        "{x,y,vx,vy,r,hp}, items carry {x,y}, orbs carry {x,y,got}. A "
        "collision part cannot be written against three shapes.",
    ),
    (
        "the loop",
        "catch and fishing have no state machine and no reset(); the other "
        "seven have both. A part that ends a round has nothing to call.",
    ),
    (
        "input",
        "solved here. Templates read keys three ways (K(), keys[e.key], "
        "keys[e.key.toLowerCase()]); partsHeld is one way and the part "
        "takes the aliases as an argument.",
    ),
)


def preamble() -> str:
    """The parts, such as they are."""

    return PARTS_PREAMBLE


__all__ = [
    "CONTRACT_GAPS",
    "PARTS_PREAMBLE",
    "PREAMBLE_NAMES",
    "UNWIRED",
    "WIRED",
    "preamble",
]
