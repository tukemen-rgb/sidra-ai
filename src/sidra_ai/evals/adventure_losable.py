"""Can the adventure be lost at all, by something driving it?

C-1424, out of C-1423's unfinished record. The loss-recap line for this
template could not be measured because **no drive that loses had ever been
produced**: a hands-off hero stands where it wakes, and the four obvious
autopilots all died in the first room. The counters were never the hard
part; reaching a loss was.

What the first room actually looks like, measured rather than assumed - the
page's own ``solid()`` was asked about every tile code, and the grid was
read off ``rooms[0]``:

* The hero wakes at tile (2, 4) and the way out is tile (19, 4) - **the
  same row**, which is why walking right looks like it should work.
* Grass (code 2) sits on that row at columns 3, 5 and 7. Grass is solid
  until it is cut, so walking alone stops twenty pixels in.
* A pond (code 3) spans columns 9-11 across rows 4 and 5. A pond cannot be
  cut, so even a hero swinging all the way still stops at column 9.

So the route out exists but goes *around* something, and no amount of
holding a direction finds it. This drives a real path instead: breadth
first over the room's own grid, with everything the page's own ``solid()``
calls a wall treated as a wall.

**The sword turned out to be a red herring, and the measurement says so.**
The obvious idea is to let the route run through grass because the hero can
cut it. Driven both ways: routing *around* the grass reaches the enemies in
486 frames and loses every heart; routing *through* it never leaves the
first room at all. Cutting is slow - the swing has a cooldown and has to be
aimed - so a path that counts on it stalls with the hero pushing at a tile
that is still solid. The driver therefore does not cut, and ``cut_grass``
stays only as the knob that demonstrates this.

The whole point is to lose, so the driver walks at the enemies once it can
reach them. It is deliberately a poor player: it never dodges, never uses
the charm, and takes every hit on offer. A driver that played well would
prove nothing about whether a loss is reachable.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.adventure import ADVENTURE_SCRIPT  # noqa: F401  (contract anchor)
from sidra_ai.creation.games import generate_game

#: The request that produces this template.
REQUEST = "冒険ゲームを作って"

#: Frames the driver is given. A loss needs three hits with sixty frames of
#: mercy between them, plus the walk to the first room that has anybody in
#: it, so this is generous rather than tight.
FRAMES = 12_000

#: The route-finding itself, without any of the stubbing around it: the
#: page's grid read through its own ``solid()``, a breadth-first step
#: towards whatever this driver wants to touch, and one frame of aiming.
#: Shared source rather than a copy, so the loss-recap probe drives the
#: exact route this module measured. The caller defines the knobs
#: (``CUT_GRASS``/``MODE``) and the two harness verbs (``advHold``/
#: ``advSwing``) before splicing it in.
ROUTE_SOURCE = """
function advTile(px, py){ return [Math.floor((px - OX) / TILE), Math.floor((py - OY) / TILE)] }
/* Solid is asked of the page, at the middle of the tile, so this can never
   disagree with the collision the template runs. Grass is the exception:
   the page calls it solid and the sword makes it not, so the route is
   allowed through it when the driver is permitted to cut. */
function advBlocked(tx, ty){
  if (tx < 0 || ty < 0 || tx >= GW || ty >= GH) return true;
  const code = rooms[room][ty][tx];
  if (code === 2) return !CUT_GRASS;
  return solid(OX + tx * TILE + TILE / 2, OY + ty * TILE + TILE / 2) }
/* Breadth first over this room's own grid. Returns the next tile to walk
   to, or null when there is no route at all. */
function advNext(goals){
  const start = advTile(hero.x, hero.y);
  const key = (x, y) => y * GW + x;
  const want = {}; goals.forEach(g => { want[key(g[0], g[1])] = true });
  const from = {}, seen = {}; const queue = [start];
  seen[key(start[0], start[1])] = true;
  let found = null;
  while (queue.length && !found) {
    const [x, y] = queue.shift();
    if (want[key(x, y)] && !(x === start[0] && y === start[1])) { found = [x, y]; break }
    [[1,0],[-1,0],[0,1],[0,-1]].forEach(([dx, dy]) => {
      const nx = x + dx, ny = y + dy, k = key(nx, ny);
      if (seen[k] || advBlocked(nx, ny)) return;
      seen[k] = true; from[k] = [x, y]; queue.push([nx, ny]) }) }
  if (!found) return null;
  let cur = found;
  while (true) {
    const prev = from[key(cur[0], cur[1])];
    if (!prev || (prev[0] === start[0] && prev[1] === start[1])) return cur;
    cur = prev } }
/* Where this driver wants to be: on top of an enemy if the room has one,
   otherwise at the way out. Standing on an enemy is the point - the hit is
   what is being measured. */
function advGoals(){
  const live = (enemies[room] || []).filter(en => en.alive);
  if (live.length) { return live.map(en => advTile(en.x, en.y)) }
  const out = [];
  for (let y = 0; y < GH; y++) { for (let x = 0; x < GW; x++) {
    if (rooms[room][y][x] === 5) { out.push([x, y]) } } }
  return out }
/* One frame's worth of aiming, as a function so the recap probe can drive
   the same route without a second copy of it. The caller supplies
   ``advHold`` (hold exactly these arrows) and ``advSwing`` (one swing). */
function advAim(f){
  /* 'naive' is what this looked like before the path: walk straight at the
     target and hope. It is kept because it is the control - it is the
     behaviour that spent a whole cycle stuck in the first room. */
  const step = MODE === 'naive' ? (advGoals()[0] || null) : advNext(advGoals());
  const want = [];
  if (step) {
    const tx = OX + step[0] * TILE + TILE / 2, ty = OY + step[1] * TILE + TILE / 2;
    if (tx - hero.x > 2) { want.push('ArrowRight') } else if (hero.x - tx > 2) { want.push('ArrowLeft') }
    if (ty - hero.y > 2) { want.push('ArrowDown') } else if (hero.y - ty > 2) { want.push('ArrowUp') }
    /* Facing the next tile and it is grass: cut it. The swing is aimed by
       hero.dir, which the arrows above have just set. */
    if (CUT_GRASS && rooms[room][step[1]][step[0]] === 2 && f % 6 === 0) { advSwing() }
  }
  return want }
"""

_DRIVER = """
const advNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : advNothing),
  apply: () => advNothing, set: () => true });
const advH = {};
globalThis.matchMedia = () => ({ matches: false, addEventListener(){}, addListener(){} });
let advClock = 0;
globalThis.performance = { now: () => advClock };
globalThis.addEventListener = (type, fn) => { (advH[type] = advH[type] || []).push(fn) };
globalThis.Image = function(){ return advNothing };
const advStore = {};
globalThis.localStorage = { getItem: (k) => (k in advStore ? advStore[k] : null),
  setItem: (k, v) => { advStore[k] = String(v) }, removeItem: (k) => { delete advStore[k] } };
globalThis.location = { reload: () => {} };
globalThis.KeyboardEvent = function(t, i){ return Object.assign({ type: t }, i) };
globalThis.dispatchEvent = (e) => { (advH[e.type] || []).forEach(fn => fn(e)); return true };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => advNothing, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {}, addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => advNothing }) };
let advQ = null;
globalThis.requestAnimationFrame = (fn) => { advQ = fn; return 1 };
SCRIPT_PLACEHOLDER
const CUT_GRASS = CUT_INPUT, MODE = MODE_INPUT;
let advFrame = 0;
function advKey(type, key){ (advH[type] || []).forEach(fn => fn({ key: key, code: key,
  preventDefault(){}, stopImmediatePropagation(){} })) }
const ARROWS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
function advHold(want){ ARROWS.forEach(k => {
  advKey(want.indexOf(k) >= 0 ? 'keydown' : 'keyup', k) }) }
function advSwing(){ advKey('keydown', ' '); advKey('keyup', ' ') }
function advStep(){ if (!advQ) return false;
  const fn = advQ; advQ = null; advClock += 50 / 3; fn(advFrame++ * 16); return true }
advKey('keydown', ' '); advKey('keyup', ' ');
advStep(); advStep();
ROUTE_TOKEN
const hits = [];
let lastHp = hero.hp;
for (let f = 0; f < FRAMES; f++) {
  advHold(advAim(f));
  if (!advStep()) break;
  if (hero.hp !== lastHp) { hits.push({ f: f, hp: hero.hp, room: room }); lastHp = hero.hp }
  if (state !== 'play') break;
}
console.log(JSON.stringify({ hp: hero.hp, state: state, room: room,
  hits: hits, frames: advFrame, cut: CUT_GRASS, mode: MODE,
  reached: (enemies[room] || []).filter(en => en.alive).length }));
"""


@dataclass(frozen=True)
class Drive:
    """One run of the driver, as the page reported it."""

    hp: int
    state: str
    room: int
    hits: tuple
    frames: int
    cut: bool
    mode: str

    @property
    def lost(self) -> bool:
        """Did the hero actually lose, rather than merely get hurt?"""

        return self.state == "over" and self.hp <= 0


def drive(
    *, mode: str = "path", cut_grass: bool = False, frames: int = FRAMES
) -> Drive | None:
    """Play the real page and report what happened. ``None`` without node."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return None
    page = generate_game(REQUEST).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    if found is None:  # pragma: no cover - the page always has one
        return None
    source = (
        _DRIVER.replace("SCRIPT_PLACEHOLDER", found.group(1))
        .replace("CUT_INPUT", "true" if cut_grass else "false")
        .replace("ROUTE_TOKEN", ROUTE_SOURCE)
        .replace("MODE_INPUT", json.dumps(mode))
        .replace("FRAMES", str(int(frames)))
    )
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    if run.returncode != 0:
        raise ValueError(run.stderr.strip()[:120])
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    return Drive(
        hp=seen["hp"],
        state=seen["state"],
        room=seen["room"],
        hits=tuple(tuple(h.items()) for h in seen["hits"]),
        frames=seen["frames"],
        cut=seen["cut"],
        mode=seen["mode"],
    )


#: The same route, wired for the loss-recap probe instead of this module's
#: own stubs. Returned as ``(setup, step)`` for ``recap.probe_source``: the
#: setup installs the knobs and the two harness verbs the route asks for,
#: the step aims one frame. The recap probe presses with ``press``/
#: ``release`` and holds nothing between frames, so the arrows are tracked
#: here and only released when the route stops wanting them.
RECAP_SETUP = (
    """
const CUT_GRASS = false, MODE = 'path';
const ARROWS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
const advDown = {};
function advHold(want){ ARROWS.forEach(k => {
  if (want.indexOf(k) >= 0) { press(k); advDown[k] = true }
  else if (advDown[k]) { release(k); advDown[k] = false } }) }
function advSwing(){ press(' '); release(' ') }
/* Hearts watched rather than damage counted - the same go, measured a
   second way. The page counts at its two damage sites; this counts drops
   in hero.hp and notes which room they happened in. A page whose counters
   were wired to the wrong site, or double-counted, disagrees with this
   without either number changing on its own. */
const advHits = [];
let advLastHp = null;
function advWatch(){ if (typeof hero === 'undefined') return;
  if (advLastHp !== null && hero.hp < advLastHp) {
    advHits.push({ room: room, hp: hero.hp }) }
  advLastHp = hero.hp }
"""
    + ROUTE_SOURCE
)

#: One frame of it, for the probe's loop.
RECAP_STEP = "try{ advWatch(); advHold(advAim(f)) }catch(e){}"


def recap_route() -> tuple[str, str]:
    """The route as ``recap.probe_source`` wants it."""

    return RECAP_SETUP, RECAP_STEP


#: What the loss-recap line has to survive, asked of the page that just
#: lost. Appended after ``recap.probe_source``'s own report, so the judge
#: reads two JSON lines: the recap probe's, then this one.
#:
#: The counters are moved and the line re-read rather than a second
#: implementation of "largest cause" being written out here. Three
#: questions, all of them about the product's own rule:
#:
#: * the hearts, watched instead of counted, agree with the two counters;
#: * make the guardian the larger cause and the line names the guardian -
#:   so the choice is a comparison, not the only clause that was ever
#:   reachable, and the count it prints follows the counter that moved;
#: * zero both and the line says nothing at all.
_RECAP_TAIL = """
/* The win case above left the page's state where a win would put it. The
   line only speaks about a loss, so put it back before asking again. */
state = 'over';
const advSaidRoam = recapLine();
const keepRoam = hurtRoam, keepGuard = hurtGuard;
hurtGuard = keepRoam + 5;
const advSaidGuard = recapLine();
hurtRoam = 0; hurtGuard = 0;
const advSaidNothing = recapLine();
hurtRoam = keepRoam; hurtGuard = keepGuard;
console.log(JSON.stringify({
  hits: advHits, roam: hurtRoam, guard: hurtGuard,
  said: advSaidRoam, saidGuard: advSaidGuard, saidNothing: advSaidNothing,
}));
"""


def recap_probe_source(script: str, *, frames: int = FRAMES) -> str:
    """The loss-recap probe, driven along this module's route and then asked
    the three questions above. Two JSON lines out."""

    from sidra_ai.creation.recap import probe_source

    return (
        probe_source(script, template="adventure", frames=frames, route=recap_route())
        + _RECAP_TAIL
    )


__all__ = [
    "Drive",
    "FRAMES",
    "RECAP_SETUP",
    "RECAP_STEP",
    "REQUEST",
    "ROUTE_SOURCE",
    "drive",
    "recap_probe_source",
    "recap_route",
]
