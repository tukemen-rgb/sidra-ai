"""Does each of the dungeon's locks refuse the player who has no key?

§3 is the lock-and-key section: a lock stops progress, a key opens it, and the
kinds of key include a tool, an ability, a **piece of knowledge** and an event
flag. §34 事実 1 gives the test for whether a lock is a lock at all - **an
agent that lacks the key must not be able to open it** - and adventure is the
one template where that can be asked without a competent player, because every
lock is a tile: stand beside it and swing.

Six locks ship in the dungeon:

1. grass, opened by the sword;
2. the chest's door, opened by the key the cave's enemies drop;
3. the same door again, held shut while the guardian is alive - an event flag,
   not an item;
4. the shrine, opened by three gems (and refusing a fourth heart at the cap,
   C-1674);
5. the side door, opened by two gems - the optional one, §3's 「任意報酬」;
6. the stone's order, opened by **knowing** which marks to strike and in which
   sequence - the knowledge key §3 names.

Exactly one of them was checked. ``creation_lock_opens_with_its_key`` (C-1626)
drives a real playthrough and shows that cutting through the grass beats going
around, which is the sword's lock and nothing else. The other five could have
opened for anybody, or refused everybody, and no number would have moved.

This judge does not play the game. It puts the hero twenty pixels below a tile
and calls the page's own ``swing()`` - twenty because the blade reaches
``[-16,0,16,0][dir]*1.25`` in the facing direction, which is the page's number,
not one nudged until it worked. That is the whole reason the dungeon can be
judged this way while platformer and puzzle still cannot: a lock is a question
you can ask standing still.

**Both directions for every lock.** A judge that only asked 「does the key open
it」 is passed by a door that is always open, and one that only asked 「does it
refuse」 is passed by a door that never opens. Each lock here is counted only
when both answers came back right.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: The locks this judge is responsible for, and the key each one wants. The
#: grass is deliberately absent: C-1626 holds it from the other side, by
#: playing, and two judges over one lock is two things to keep in step.
LOCKS: tuple[tuple[str, str], ...] = (
    ("door_key", "宝箱の扉 / 鍵"),
    ("door_guard", "宝箱の扉 / 番人が倒れていること"),
    ("shrine", "祠 / 宝石 3"),
    ("side_door", "わき道の扉 / 宝石 2"),
    ("stone_order", "石碑の印 / 順番を知っていること"),
)

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)

_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function frame(){ if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
/* Re-entrancy guard: winning restarts the page from inside the handler, and
   the restart dispatches input of its own. Without this the probe calls
   itself until the stack gives out - the page is fine, the harness was
   feeding itself. */
let _inPress = false;
function press(k){ if (_inPress) return; _inPress = true;
  try { const e = probeKey(k);
    (handlers.keydown || []).forEach(fn => fn(e));
    (handlers.keyup || []).forEach(fn => fn(e)) }
  finally { _inPress = false } }
press(' '); frame(); frame();

function findTile(rm, kind){
  for (let ty = 0; ty < GH; ty++) for (let tx = 0; tx < GW; tx++)
    if (rooms[rm][ty][tx] === kind) return {tx: tx, ty: ty};
  return null }
/* 20px below the tile's centre, because the blade reaches 20px upward. */
function standBelow(rm, spot){
  room = rm; state = 'play';
  hero.x = OX + spot.tx * TILE + TILE / 2;
  hero.y = OY + spot.ty * TILE + TILE / 2 + 20;
  hero.inv = 0; hero.swing = 0; hero.queued = false; hero.dir = 0 }
/* The page's own swing(), not a key event: a keypress has to survive a frame,
   and a win restarts the page from inside the key handler. */
function useTile(){ hero.dir = 0; hero.swing = 0; swing(); for (let i = 0; i < 4; i++) frame() }

const out = {};
const door = findTile(2, 7), shrine = findTile(0, 9), side = findTile(1, 10);
const marks = [findTile(1, 13), findTile(1, 14), findTile(1, 15)];
out.found = { door: !!door, shrine: !!shrine, side: !!side,
              marks: marks.filter(Boolean).length, stone: !!findTile(0, 12) };

if (door) {
  /* One lock at a time. Asking for the key while the guardian is also alive
     lets the guardian's refusal stand in for the key's: the door could stop
     looking at `hero.key` altogether and this would still read as shut.
     Found by destruction - the sabotage that deleted the key check walked
     straight through the first version of this. */
  standBelow(2, door); hero.key = false; if (guard) guard.alive = false;
  useTile(); out.doorNoKey = { state: state, msg: msg };
  standBelow(2, door); hero.key = true; if (guard) guard.alive = true;
  useTile(); out.doorKeyGuard = { state: state, msg: msg };
  standBelow(2, door); hero.key = true; if (guard) guard.alive = false;
  useTile(); out.doorKeyNoGuard = { state: state, msg: msg };
}
state = 'play';
if (shrine) {
  standBelow(0, shrine); hero.gems = 2; hero.maxhp = 3; hero.hp = 3;
  useTile(); out.shrineShort = { gems: hero.gems, maxhp: hero.maxhp };
  standBelow(0, shrine); hero.gems = 3;
  useTile(); out.shrinePaid = { gems: hero.gems, maxhp: hero.maxhp };
  standBelow(0, shrine); hero.gems = 9; hero.maxhp = HP_CAP; hero.hp = HP_CAP;
  useTile(); out.shrineFull = { gems: hero.gems, maxhp: hero.maxhp };
}
if (side) {
  standBelow(1, side); hero.gems = 1;
  useTile(); out.sideShort = { tile: rooms[1][side.ty][side.tx], gems: hero.gems };
  standBelow(1, side); hero.gems = 2;
  useTile(); out.sidePaid = { tile: rooms[1][side.ty][side.tx], gems: hero.gems };
}
if (marks.every(Boolean)) {
  /* Underscored: the page has its own `knock(mark,tx,ty)`, and a probe that
     declares `knock` replaces it - the page's swing() then calls the probe's
     and the whole thing eats itself. Same class of collision as a probe
     declaring `let score` next to a page that already has one. */
  function _probeKnock(order){
    kprog = 0; ksolved = false; keyDrop = null; hero.key = false;
    for (const idx of order) { standBelow(1, marks[idx]); useTile() }
    return { kprog: kprog, solved: ksolved } }
  const right = KORDER.slice();
  const wrong = right.slice().reverse();
  out.korder = right;
  out.knockWrong = _probeKnock(
    wrong.join('') === right.join('') ? [right[0], right[0], right[0]] : wrong);
  out.knockRight = _probeKnock(right);
}
console.log(JSON.stringify(out));
"""


@dataclass(frozen=True)
class LocksResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    held: int = 0
    locks: tuple[str, ...] = ()


def _drive(request: str = "ゲームを作って") -> dict | None:
    page = generate_game(request, template="adventure").html
    script = _SCRIPT.search(page)
    if script is None:
        return None
    try:
        run = subprocess.run(
            ["node", "-"],
            input=_PROBE.replace("SCRIPT_PLACEHOLDER", script.group(1)),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if run.returncode != 0:
            return None
        return json.loads(run.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def evaluate_adventure_locks_hold() -> LocksResult:
    checks = 0
    failures: list[str] = []
    held: list[str] = []

    seen = _drive()
    if seen is None:
        return LocksResult(False, 0, 1, ("運転器が動かせない",))

    found = seen.get("found") or {}
    for name in ("door", "shrine", "side", "stone"):
        if found.get(name):
            checks += 1
        else:
            failures.append(f"{name}: そのタイルが地図に無い")
    if found.get("marks") == 3:
        checks += 1
    else:
        failures.append(f"marks: 印が 3 つない（{found.get('marks')}）")

    def lock(key: str, shut: bool, open_: bool, why: str) -> None:
        nonlocal checks
        if shut:
            checks += 1
        else:
            failures.append(f"{key}: 鍵なしで開く（{why}）")
        if open_:
            checks += 1
        else:
            failures.append(f"{key}: 鍵があっても開かない（{why}）")
        if shut and open_:
            held.append(key)

    if "doorNoKey" in seen:
        lock(
            "door_key",
            seen["doorNoKey"].get("state") != "win",
            seen["doorKeyNoGuard"].get("state") == "win",
            "宝箱の扉と鍵",
        )
        lock(
            "door_guard",
            seen["doorKeyGuard"].get("state") != "win",
            seen["doorKeyNoGuard"].get("state") == "win",
            "番人が倒れていること",
        )
    else:
        failures.append("door_key: 扉を試せていない")
        failures.append("door_guard: 番人を試せていない")

    if "shrinePaid" in seen:
        short, paid, full = seen["shrineShort"], seen["shrinePaid"], seen["shrineFull"]
        lock(
            "shrine",
            short.get("maxhp") == 3 and short.get("gems") == 2,
            paid.get("maxhp") == 4 and paid.get("gems") == 0,
            "祠と宝石 3",
        )
        # C-1674's ceiling is part of the same lock: a sink that takes payment
        # and returns nothing is not a sink.
        if full.get("gems") == 9:
            checks += 1
        else:
            failures.append("shrine: 天井で宝石を取り上げる")
    else:
        failures.append("shrine: 祠を試せていない")

    if "sidePaid" in seen:
        lock(
            "side_door",
            seen["sideShort"].get("tile") == 10 and seen["sideShort"].get("gems") == 1,
            seen["sidePaid"].get("tile") == 0 and seen["sidePaid"].get("gems") == 0,
            "わき道の扉と宝石 2",
        )
    else:
        failures.append("side_door: わき道を試せていない")

    if "knockRight" in seen:
        lock(
            "stone_order",
            not seen["knockWrong"].get("solved"),
            bool(seen["knockRight"].get("solved")),
            "石碑の順番という知識",
        )
    else:
        failures.append("stone_order: 石碑を試せていない")

    want = len(LOCKS)
    if len(held) == want:
        checks += 1
    else:
        failures.append(f"{len(held)}/{want} の錠しか両方向で確かめていない")

    return LocksResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        held=len(held),
        locks=tuple(held),
    )


__all__ = ["LOCKS", "LocksResult", "evaluate_adventure_locks_hold"]
