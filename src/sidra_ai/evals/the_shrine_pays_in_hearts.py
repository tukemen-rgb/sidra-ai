"""Does the shrine's payment show up on the screen?

C-1984, §5 ("収集物に意味のある目的が無ければ、プレイヤーは収集物どころか
ゲーム自体への興味を失う" - a tap needs a sink).

Three judges already watch this sink - ``creation_gem_sink``,
``creation_sink_affordable``, ``creation_sink_returns_value`` - and all
three read the books in a node probe: ``hero.maxhp``, ``hero.gems``. What
the player receives is not a book. The hearts are ``fillRect``s in the
HUD; a page whose numbers rose while its heart row stayed the same would
have taken three gems and shown nothing for them, and no judge would move.

So this drives the real page and counts painted hearts:

1. with three gems, one swing at the shrine adds exactly one heart's worth
   of paint to the HUD band,
2. with two, nothing is added (what cannot be paid cannot be received),
3. at the ceiling (``HP_CAP``) nothing is added *and* the gems stay - the
   refusal C-1674 found, now visible as well as booked,
4. the new heart is still painted sixty frames later: a possession, not a
   flourish.

**How the shrine is reached.** It is used by swinging at it, not by
standing on it, so the probe finds the shrine tile in the room's own grid,
places the hero one tile to its left facing right, and presses space once.
The key pair comes from ``probekeys`` (C-1651's ratchet). Hearts are the
theme's alert colour, counted only inside the HUD band, so the same colour
elsewhere on the playfield cannot be mistaken for one.
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
from sidra_ai.creation.themes import select_theme
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

ASK = "ふくろうの冒険ゲームを作って"

#: One filled heart is 14x10 (adventure's HUD), so a heart's worth of paint
#: is 140 pixels. The floor allows for the outline the row also draws.
HEART = 140

#: The band the HUD owns, in canvas pixels. Below it is the world, which
#: paints the same colour on enemies.
BAND = 14

_TITLE = re.compile(r"<title>SHRINE(.*?)</title>", re.S)

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
      const want = [HEART_R, HEART_G, HEART_B];
      /* Hearts, and only hearts: the HUD band, not the world below it. */
      const hearts = function(){
        const d = cx.getImageData(0, 0, cv.width, BAND_TOKEN).data;
        let n = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] === want[0] && d[i + 1] === want[1] && d[i + 2] === want[2]) n++ }
        return n };
      /* The shrine is swung at, not stood on. */
      const place = function(gems){
        let sx = -1, sy = -1;
        const grid = rooms[room];
        for (let y = 0; y < grid.length; y++) {
          for (let x = 0; x < grid[y].length; x++) { if (grid[y][x] === 9) { sx = x; sy = y } } }
        if (sx < 0) return false;
        hero.gems = gems;
        hero.x = OX + (sx - 1) * TILE + TILE / 2;
        hero.y = OY + sy * TILE + TILE / 2;
        hero.dir = 1;
        hero.swing = 0;
        return true };
      out.found = place(3);
      if (!out.found) { document.title = 'SHRINE' + JSON.stringify(out); return }
      out.cap = HP_CAP;
      out.beforePaid = hearts();
      out.maxBefore = hero.maxhp;
      press();
      step(12);
      out.afterPaid = hearts();
      out.maxAfter = hero.maxhp;
      out.gemsAfterPaid = hero.gems;
      step(60);
      out.laterPaid = hearts();
      /* Too few gems: the same swing, nothing to receive. */
      place(2);
      step(12);
      const short0 = hearts();
      press();
      step(12);
      out.shortDelta = hearts() - short0;
      out.gemsAfterShort = hero.gems;
      /* The ceiling: full hearts, three gems, and the shrine must refuse. */
      hero.maxhp = HP_CAP;
      hero.hp = HP_CAP;
      place(3);
      step(12);
      const full0 = hearts();
      press();
      step(12);
      out.fullDelta = hearts() - full0;
      out.gemsAfterFull = hero.gems;
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'SHRINE' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class ShrineResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def read_page() -> dict:
    """Drive the shrine three ways and report the painted hearts."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    raw = select_theme(ASK).tokens["alert"].lstrip("#")
    heart = tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
    body = with_probe_keys(
        _REPORT.replace("HEART_R", str(heart[0]))
        .replace("HEART_G", str(heart[1]))
        .replace("HEART_B", str(heart[2]))
        .replace("BAND_TOKEN", str(BAND))
    )
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


def evaluate_the_shrine_pays_in_hearts() -> ShrineResult:
    total = 4
    seen = read_page()
    if "err" in seen or not seen.get("found"):
        return ShrineResult(0, total, (str(seen.get("err", "no shrine in the room")),))

    passed = 0
    failures: list[str] = []
    paid = seen["afterPaid"] - seen["beforePaid"]
    if paid >= HEART:
        passed += 1
    else:
        failures.append(
            f"three gems bought {paid} pixels of heart, not {HEART} "
            f"(the books went {seen['maxBefore']} -> {seen['maxAfter']})"
        )
    if seen["shortDelta"] == 0:
        passed += 1
    else:
        failures.append(f"two gems still painted {seen['shortDelta']} pixels")
    if seen["fullDelta"] == 0 and seen["gemsAfterFull"] == 3:
        passed += 1
    else:
        failures.append(
            f"at the ceiling the row moved {seen['fullDelta']} and "
            f"{3 - seen['gemsAfterFull']} gems were taken"
        )
    if seen["laterPaid"] >= seen["afterPaid"]:
        passed += 1
    else:
        failures.append(
            f"the new heart faded: {seen['afterPaid']} -> {seen['laterPaid']}"
        )
    readings = (
        f"hearts {seen['beforePaid']}->{seen['afterPaid']} (+{paid}px, "
        f"still {seen['laterPaid']} later) / two gems {seen['shortDelta']}px / "
        f"at the cap {seen['fullDelta']}px, gems left {seen['gemsAfterFull']}",
    )
    return ShrineResult(passed, total, tuple(failures[:3]), readings)


__all__ = [
    "ASK",
    "BAND",
    "HEART",
    "ShrineResult",
    "evaluate_the_shrine_pays_in_hearts",
    "read_page",
]
