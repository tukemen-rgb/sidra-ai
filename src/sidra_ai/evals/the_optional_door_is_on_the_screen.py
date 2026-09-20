"""Is the branch a door the player can see, pay for, and be refused by?

C-1985, §3 ("面白さの最低条件は分岐 1 つ＋任意報酬 1 つ"; hard locks open
only to their price).

Four judges already watch adventure's locks - ``lock_opens_with_its_key``,
``adventure_locks_hold``, ``knowledge_key``, ``soft_route`` - and all four
read the world array and the state flags in a node probe. To a player a
lock is not an array: it is a door drawn on the screen, and "it opened" is
paint that went away.

So this drives the real page and reads the tiles:

1. before paying, the door's own colour fills its square - an invisible
   lock is not a lock,
2. two gems and one swing take that paint away - the way opens on screen,
3. one gem leaves it exactly as it was - the hard lock holds,
4. the charm behind it is painted - §3's optional reward is a thing in the
   world, not a flag.

The door is swung at, like the shrine (C-1984), so the probe finds the
tile in the room's own grid, stands the hero beside it facing it, and
presses space once. Colours are read inside the tile's square only, so the
same colour elsewhere cannot be mistaken for a door.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import with_probe_keys
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

ASK = "ふくろうの冒険ゲームを作って"

#: How much of the door's own square must change when it is paid for.
#: Measured: paying moved 0.608 of it, a refused swing 0.048.
OPENS = 0.3

#: How little may move when the payment is refused. Not zero: the cave is
#: lit by moving glows, so the same square drifts a little every frame.
HOLDS = 0.15

#: A door that came back would move about as much as it did when it went
#: (0.6); the drift over sixty frames measured 0.117.
STAYS = 0.3

#: The charm leaves the screen when it is taken (measured: all of it).
TAKEN = 0.2

_TITLE = re.compile(r"<title>DOOR(.*?)</title>", re.S)

_HOOK = """
<script>
window.__q = [];
window.requestAnimationFrame = function(fn){ window.__q.push(fn); return window.__q.length };
</script>
"""

_REPORT = """
<script>
PROBE_KEYS_PLACEHOLDER
addEventListener('load', function(){
  setTimeout(function(){
    const out = {};
    try {
      let T = 0;
      const step = function(n){
        for (let k = 0; k < n && window.__q.length; k++) {
          const due = window.__q; window.__q = []; T += 16;
          due.forEach(function(fn){ fn(T) }) } };
      const pair = probeKey(' ');
      const press = function(){
        ['keydown', 'keyup'].forEach(function(type){
          const e = new KeyboardEvent(type, {key: pair.key, code: pair.code,
            bubbles: true, cancelable: true});
          document.dispatchEvent(e); window.dispatchEvent(e); }) };
      step(4);
      press();
      step(20);
      const cv = document.querySelector('canvas');
      const cx = cv.getContext('2d');
      const find = function(what){
        const grid = rooms[room];
        for (let y = 0; y < grid.length; y++) {
          for (let x = 0; x < grid[y].length; x++) { if (grid[y][x] === what) return [x, y] } }
        return null };
      /* The cave is lit by glows, so a tile's colour is not a constant:
         the same wood under the hero's light is not the wood two squares
         away. What does hold is the difference between two squares side by
         side under the same light - a door does not look like a floor. */
      /* The cave is lit by glows, so two squares never look alike: the
         light itself differs across the room. What holds is the same
         square before and after - the door's own pixels, from the same
         place, with the hero standing still. */
      const snap = function(at){
        const d = cx.getImageData(OX + at[0] * TILE, OY + at[1] * TILE, TILE, TILE).data;
        return Uint8ClampedArray.from(d) };
      const changed = function(a, b){
        let n = 0;
        for (let i = 0; i < a.length; i += 4) {
          if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]) n++ }
        return +(n / (a.length / 4)).toFixed(3) };
      /* The door is not in the first room. Walking onto the forward tile
         (5) is what moves the hero on, and moveHero() runs every frame, so
         standing there and turning one frame is the page's own way through. */
      const hop = function(){
        const gate = find(5);
        if (!gate) return false;
        hero.x = OX + gate[0] * TILE + TILE / 2;
        hero.y = OY + gate[1] * TILE + TILE / 2;
        step(2);
        return true };
      let door = find(10), hops = 0;
      while (!door && hops < 3 && hop()) { door = find(10); hops++ }
      out.hops = hops;
      const charm = find(11);
      out.door = !!door;
      out.charm = !!charm;
      if (!door) { document.title = 'DOOR' + JSON.stringify(out); return }
      const stand = function(at, dx, gems){
        if (gems !== null) hero.gems = gems;
        hero.x = OX + (at[0] + dx) * TILE + TILE / 2;
        hero.y = OY + at[1] * TILE + TILE / 2;
        hero.dir = dx < 0 ? 1 : 3;
        hero.swing = 0; };
      stand(door, -1, 1);
      step(10);
      const shut = snap(door);
      /* One gem is not two: the lock holds, and the square does not move. */
      press();
      step(14);
      const afterShort = snap(door);
      out.shortMoved = changed(shut, afterShort);
      out.gemsAfterShort = hero.gems;
      /* Two gems: the way opens where the player is looking. */
      hero.gems = 2;
      step(4);
      const paidBefore = snap(door);
      press();
      step(14);
      const paid = snap(door);
      out.paidMoved = changed(paidBefore, paid);
      out.gemsAfterPaid = hero.gems;
      step(60);
      out.stayedOpen = changed(paid, snap(door));
      /* The reward behind it: taken, it leaves the screen. */
      if (charm) {
        const before = snap(charm);
        hero.x = OX + charm[0] * TILE + TILE / 2;
        hero.y = OY + charm[1] * TILE + TILE / 2;
        step(6);
        stand(charm, -1, null);
        step(8);
        out.charmTaken = changed(before, snap(charm));
        out.hasCharm = !!hero.charm;
      } else { out.charmTaken = 0; out.hasCharm = false }
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'DOOR' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class DoorResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def read_page() -> dict:
    """Drive the optional door twice - unpaid and paid - and read the tiles."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    body = with_probe_keys(_REPORT)
    html = generate_game(ASK).html
    with tempfile.TemporaryDirectory() as room:
        page = pathlib.Path(room) / "page.html"
        page.write_text(
            html.replace("<body", _HOOK + "<body", 1).replace("</body>", body + "</body>"),
            encoding="utf-8",
        )
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--force-prefers-reduced-motion",
                "--virtual-time-budget=9000",
                "--window-size=390,844",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    return json.loads(found.group(1)) if found else {"err": "the page said nothing"}


def evaluate_the_optional_door_is_on_the_screen() -> DoorResult:
    total = 4
    seen = read_page()
    if "err" in seen or not seen.get("door"):
        return DoorResult(0, total, (str(seen.get("err", "no optional door in the room")),))

    passed = 0
    failures: list[str] = []
    if seen["paidMoved"] >= OPENS and seen["gemsAfterPaid"] == 0:
        passed += 1
    else:
        failures.append(
            f"two gems moved {seen['paidMoved']} of the door's square and left "
            f"{seen['gemsAfterPaid']} gems"
        )
    if seen["shortMoved"] <= HOLDS and seen["gemsAfterShort"] == 1:
        passed += 1
    else:
        failures.append(
            f"one gem moved {seen['shortMoved']} of it and left "
            f"{seen['gemsAfterShort']} gems"
        )
    if seen["stayedOpen"] <= STAYS:
        passed += 1
    else:
        failures.append(f"the door came back: {seen['stayedOpen']} moved after sixty frames")
    if seen["charm"] and seen["charmTaken"] >= TAKEN and seen["hasCharm"]:
        passed += 1
    else:
        failures.append(
            f"the reward behind the door moved {seen['charmTaken']} and the hero "
            f"{'has' if seen.get('hasCharm') else 'has not'} it"
        )

    readings = (
        f"door: paid {seen['paidMoved']} / refused {seen['shortMoved']} / "
        f"after sixty frames {seen['stayedOpen']} / charm {seen['charmTaken']} "
        f"(hero has it: {seen.get('hasCharm')})",
    )
    return DoorResult(passed, total, tuple(failures[:3]), readings)


__all__ = [
    "ASK",
    "HOLDS",
    "OPENS",
    "STAYS",
    "TAKEN",
    "DoorResult",
    "evaluate_the_optional_door_is_on_the_screen",
    "read_page",
]
