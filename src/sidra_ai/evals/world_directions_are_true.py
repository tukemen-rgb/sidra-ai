"""Is the dungeon's own signposting true about the dungeon?

§3 draws progression as a mission graph; §30 says a game should not make the
player hold it in their head, so adventure tells them: an NPC in the forest
says 「東の洞窟の敵が鍵を守っている。祭壇の宝を頼む。」, the locked door repeats
where the key is, and a stone says which marks to strike and where they are.

Those sentences are claims about the map. Nothing checked them.
``game_words_match_the_page`` (C-1855) checks that the words the chat uses are
the page's own words - vocabulary, not geography.
``creation_adventure_locks_hold`` (C-1887) checks that each lock wants its key
- mechanism, not directions. Between them, a change to room generation could
leave the stone pointing at the wrong room and every number would stay green.

**The sentences are read off the running page, never written here.** A judge
holding its own copy of 「東の洞窟…」 goes green against a page that now says
something else, which is C-1640's ledger problem in its plainest form. The
probe stands the hero beside the NPC, the door and the stone, uses each, and
keeps whatever the page actually said.

**A place is named when the sentence carries a fragment of that room's name
that belongs to no other room.** 「洞窟」 identifies 「ひかり苔の洞窟」 and
appears in no other name, so a sentence containing it is pointing there. That
rule is why the judge does not need to know the words: it compares the page's
sentences against the page's own ``NAMES``.

**Both directions.** A judge that only asked 「is the direction correct」 is
satisfied by a stone that says nothing at all - so each claim is counted only
when the sentence was printed AND its content checks out against the map.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: The claims this judge holds, in the order it reports them.
CLAIMS: tuple[tuple[str, str], ...] = (
    ("npc_key_room", "NPC が鍵のある部屋を名指す"),
    ("npc_treasure_room", "NPC が宝のある部屋を名指す"),
    ("door_key_room", "閉じた扉が鍵のある部屋を名指す"),
    ("stone_marks_room", "石碑が印のある部屋を名指す"),
    ("stone_reads_the_order", "石碑が読み上げる順が本当の順"),
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
/* The page has its own knock(); a probe that declares one replaces it
   (C-1887). Nothing here takes a name the page uses. */
function _probeFind(rm, kind){
  const out = [];
  for (let ty = 0; ty < GH; ty++) for (let tx = 0; tx < GW; tx++)
    if (rooms[rm][ty][tx] === kind) out.push({tx: tx, ty: ty});
  return out }
/* 20px below the tile, because the blade reaches 20px up. */
function _probeStand(rm, spot){
  room = rm; state = 'play';
  hero.x = OX + spot.tx * TILE + TILE / 2;
  hero.y = OY + spot.ty * TILE + TILE / 2 + 20;
  hero.inv = 0; hero.swing = 0; hero.queued = false; hero.dir = 0 }
function _probeUse(rm, spot){
  _probeStand(rm, spot); msg = '';
  hero.swing = 0; swing(); for (let i = 0; i < 4; i++) frame();
  return msg }

const out = { names: NAMES.slice(), order: KORDER.map(i => KMARKS[i]) };
const where = {};
for (const [name, kind] of [['npc', 8], ['stone', 12], ['door', 7]]) {
  for (let r = 0; r < rooms.length; r++) {
    const hit = _probeFind(r, kind);
    if (hit.length) { where[name] = { room: r, spot: hit[0] }; break } } }
out.rooms = {};
for (const k of Object.keys(where)) out.rooms[k] = where[k].room;
/* Where the marks are. */
for (let r = 0; r < rooms.length; r++) {
  const marks = _probeFind(r, 13).length + _probeFind(r, 14).length + _probeFind(r, 15).length;
  if (marks === 3) { out.rooms.marks = r; break } }
/* Where the key really comes from: kill a room's last enemy and see whether a
   key falls. Driven, not read off the source - the drop is a consequence. */
out.rooms.key = null;
for (let r = 0; r < rooms.length; r++) {
  if (!enemies[r] || !enemies[r].length) continue;
  room = r; state = 'play'; keyDrop = null; hero.key = false;
  enemies[r].forEach((e, i) => { e.alive = (i === 0) });
  const en = enemies[r][0];
  hero.x = 200; hero.y = 160; hero.dir = 1; hero.inv = 0;
  en.x = hero.x + 20; en.y = hero.y; en.t = 999;
  for (let i = 0; i < 40 && en.alive; i++) { hero.swing = 0; hero.dir = 1; swing(); frame() }
  if (keyDrop) { out.rooms.key = r; break } }

state = 'play';
hero.key = false;
out.said = {};
if (where.npc) out.said.npc = _probeUse(where.npc.room, where.npc.spot);
if (where.stone) out.said.stone = _probeUse(where.stone.room, where.stone.spot);
if (where.door) { hero.key = false; if (guard) guard.alive = true;
  out.said.door = _probeUse(where.door.room, where.door.spot) }
console.log(JSON.stringify(out));
"""


@dataclass(frozen=True)
class DirectionsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    true_claims: int = 0
    claims: tuple[str, ...] = ()


def _fragments(name: str, others: list[str]) -> list[str]:
    """Substrings of ``name`` (length >= 2) that no other room's name carries.

    A place is named when the sentence carries one of these. Deriving them
    from ``NAMES`` rather than listing 「洞窟」 here is what lets the judge stay
    right when the generator renames a room.
    """

    out = []
    for size in range(2, len(name) + 1):
        for start in range(0, len(name) - size + 1):
            piece = name[start : start + size]
            if all(piece not in other for other in others):
                out.append(piece)
    return out


def _names_room(sentence: str, room: int, names: list[str]) -> bool:
    others = [n for i, n in enumerate(names) if i != room]
    return any(piece in sentence for piece in _fragments(names[room], others))


def evaluate_world_directions_are_true() -> DirectionsResult:
    checks = 0
    failures: list[str] = []
    true_claims: list[str] = []

    page = generate_game("ゲームを作って", template="adventure").html
    script = _SCRIPT.search(page)
    if script is None:
        return DirectionsResult(False, 0, 1, ("頁に script が無い",))
    try:
        run = subprocess.run(
            ["node", "-"],
            input=_PROBE.replace("SCRIPT_PLACEHOLDER", script.group(1)),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if run.returncode != 0:
            return DirectionsResult(False, 0, 1, ("運転器が動かせない",))
        seen = json.loads(run.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError):
        return DirectionsResult(False, 0, 1, ("運転器が動かせない",))

    names = list(seen.get("names") or [])
    rooms = seen.get("rooms") or {}
    said = seen.get("said") or {}

    def claim(key: str, spoke: bool, right: bool, why: str) -> None:
        nonlocal checks
        if spoke:
            checks += 1
        else:
            failures.append(f"{key}: 何も言わない（{why}）")
        if right:
            checks += 1
        else:
            failures.append(f"{key}: 言っていることが地図と違う（{why}）")
        if spoke and right:
            true_claims.append(key)

    npc = said.get("npc") or ""
    door = said.get("door") or ""
    stone = said.get("stone") or ""
    key_room, door_room = rooms.get("key"), rooms.get("door")
    marks_room = rooms.get("marks")

    if key_room is None or door_room is None or marks_room is None:
        failures.append(f"地図が読めない（key={key_room} door={door_room} marks={marks_room}）")
    else:
        claim(
            "npc_key_room",
            bool(npc),
            _names_room(npc, key_room, names) and "鍵" in npc,
            f"鍵は部屋 {key_room}「{names[key_room]}」",
        )
        claim(
            "npc_treasure_room",
            bool(npc),
            _names_room(npc, door_room, names) and "宝" in npc,
            f"宝は部屋 {door_room}「{names[door_room]}」",
        )
        claim(
            "door_key_room",
            bool(door),
            _names_room(door, key_room, names) and "鍵" in door,
            f"扉も鍵の在り処を言う（部屋 {key_room}）",
        )
        claim(
            "stone_marks_room",
            bool(stone),
            _names_room(stone, marks_room, names) and marks_room == key_room,
            f"印は部屋 {marks_room}",
        )
        claim(
            "stone_reads_the_order",
            bool(stone),
            "→".join(seen.get("order") or []) in stone,
            "石碑の読み上げが KORDER と一致",
        )
        # East is east: the rooms run left to right, so the cave and the altar
        # sit at higher indices than the forest the NPC speaks in.
        if 0 < key_room < door_room and "東" in npc:
            checks += 1
        else:
            failures.append(
                f"「東」が地図と合わない（key={key_room} door={door_room}）"
            )

    want = len(CLAIMS)
    if len(true_claims) == want:
        checks += 1
    else:
        failures.append(f"{len(true_claims)}/{want} の道案内しか確かめていない")

    return DirectionsResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        true_claims=len(true_claims),
        claims=tuple(true_claims),
    )


__all__ = ["CLAIMS", "DirectionsResult", "evaluate_world_directions_are_true"]
