"""Does the hit actually reach the screen - and leave when asked?

C-1979, §1. Every juice judge in this repository reads the page's own
count: ``shakeAmount()``, ``particleCount()``, ``flashFacts()``. Those are
honest numbers about intent. They are not the screen.

The shake is a CSS transform on the stage element, so a page could count a
shake that never moved anything - or, worse, move and never come back,
leaving the whole game sitting a few pixels off its own frame. The grains
are painted after the template's own draw, so a page could hold two dozen
live particles that nothing ever paints. Neither shows up in a count.

So this opens the page twice in real headless Chromium and reads the
browser, not the bookkeeping:

* the element's ``getBoundingClientRect()`` before, during and after a
  shake, and
* the canvas pixels in an 80x80 box around a burst's spawn, with and
  without the burst, over the same three frames.

The second open carries ``--force-prefers-reduced-motion``. C-1972 proved
the switch reaches the page; this asks the next question - that the motion
then *stops*, and that stopping the motion does not stop the game.

**How the frames are turned.** ``requestAnimationFrame`` is taken over
before the page's scripts run and the callbacks are run by hand, as in
C-1978. A reading taken when no callback is pending sees a still picture
and would report that nothing happened: measured during this item's own
groundwork, where catch's grains looked dead until the frames were
actually turned (they decay 0.83 -> 0.44 -> 0 like every other template).
Every reading here steps frames first.
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

ASK = "ふくろうのキャッチゲームを作って"

#: The weight handed to shake(): large enough that a real move cannot be
#: confused with rounding, small enough to stay a game's shake.
WEIGHT = 9

#: A shake that has decayed must put the element back where it was. The
#: floor for "it moved at all" is one CSS pixel.
MOVED_PX = 1.0

#: The grains are 3px squares; in a box around their spawn they outweigh
#: the world's own motion several times over (measured: 0-2.2 idle,
#: 9.6-17.7 with a burst).
GRAIN_FACTOR = 3.0

_TITLE = re.compile(r"<title>JUICEREAL(.*?)</title>", re.S)

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
      step(4);
      const cv = document.querySelector('canvas');
      const cx = cv.getContext('2d');
      const at = function(){ const r = cv.getBoundingClientRect();
        return [+r.left.toFixed(2), +r.top.toFixed(2)] };
      /* The shake is measured on the briefing screen, before the press.
         In a live catch round every dropped fruit calls shake(5) again -
         measured: SHAKE still 0.584 after 162 frames - so a game shaking
         because the player is missing would read as a shake that never
         settles. Here nothing else touches it. */
      const rest = at();
      out.rest = rest;
      shake(WEIGHT_TOKEN);
      let far = 0;
      for (let i = 0; i < 12; i++) { step(1); const p = at();
        far = Math.max(far, Math.abs(p[0] - rest[0]), Math.abs(p[1] - rest[1])) }
      out.far = +far.toFixed(2);
      step(120);
      out.settled = at();
      out.amount = (typeof shakeAmount === 'function') ? +shakeAmount().toFixed(3) : null;
      const box = function(){
        return cx.getImageData(cv.width / 2 - 40, cv.height / 2 - 40, 80, 80).data };
      const diff = function(a, b){ let d = 0;
        for (let i = 0; i < a.length; i += 4) {
          d += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]) }
        return d / (a.length / 4) };
      const overThree = function(withBurst){
        if (withBurst) { burst(cv.width / 2, cv.height / 2, 24, '#ffffff') }
        let d = 0;
        for (let i = 0; i < 3; i++) { const y1 = box(); step(1); const y2 = box(); d += diff(y1, y2) }
        return +d.toFixed(3) };
      /* The grains are read on the same still briefing screen: in a live
         round the fruit crossing the box moves more paint than two dozen
         3px grains ever will (measured: 30.2 idle against 41.6 with a
         burst - a real signal, but not one worth a threshold). */
      out.idle = overThree(false);
      out.burst = overThree(true);
      out.grains = particleCount();
      /* Do they stop? The count cannot answer it here - the briefing screen
         runs the attract demo (C-1113), whose own catches keep throwing
         grains, which is why 24 asked for reads as 46 alive. The paint can:
         forty frames later the same box must be as quiet as it was before
         the burst. */
      step(40);
      out.grainsEnd = particleCount();
      out.late = overThree(false);
      /* Now the game itself, for the one question that needs it. */
      const pair = probeKey(' ');
      ['keydown', 'keyup'].forEach(function(type){
        const e = new KeyboardEvent(type, {key: pair.key, code: pair.code, bubbles: true});
        document.dispatchEvent(e); window.dispatchEvent(e); });
      step(30);
      /* The world's own motion, so "reduced" can be told from "frozen". */
      const whole = function(){ return cx.getImageData(0, 0, cv.width, cv.height).data };
      let alive = 0;
      for (let i = 0; i < 6; i++) { const w1 = whole(); step(1); const w2 = whole();
        if (diff(w1, w2) > 0) alive++ }
      out.alive = alive;
      out.after = at();
      out.ran = T / 16;
      out.reduced = (typeof REDUCED !== 'undefined') ? !!REDUCED : null;
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'JUICEREAL' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class JuiceOnScreenResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _open(html: str, *, reduced: bool) -> dict:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    body = with_probe_keys(_REPORT.replace("WEIGHT_TOKEN", str(WEIGHT)))
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
                *(["--force-prefers-reduced-motion"] if reduced else []),
                "--virtual-time-budget=8000",
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


def read_page(*, reduced: bool) -> dict:
    """What one open of the page reports."""

    return _open(generate_game(ASK).html, reduced=reduced)


def evaluate_juice_reaches_the_screen() -> JuiceOnScreenResult:
    total = 8
    passed = 0
    failures: list[str] = []
    readings: list[str] = []

    plain = read_page(reduced=False)
    if "err" in plain:
        failures.append(f"plain: {plain['err']}")
    else:
        readings.append(
            f"plain far={plain['far']}px idle={plain['idle']} burst={plain['burst']} "
            f"late={plain['late']} grains={plain['grains']}->{plain['grainsEnd']}"
        )
        if plain["far"] >= MOVED_PX:
            passed += 1
        else:
            failures.append(f"plain: the shake moved the stage {plain['far']}px")
        if plain["settled"] == plain["rest"] and plain["amount"] == 0:
            passed += 1
        else:
            failures.append(
                f"plain: the stage settled at {plain['settled']}, not {plain['rest']} "
                f"(shake left at {plain['amount']})"
            )
        if plain["burst"] >= max(plain["idle"] * GRAIN_FACTOR, 1.0):
            passed += 1
        else:
            failures.append(
                f"plain: the grains painted {plain['burst']} against {plain['idle']} idle"
            )
        if plain["late"] * GRAIN_FACTOR <= plain["burst"]:
            passed += 1
        else:
            failures.append(
                f"plain: the grains were still painting {plain['late']} forty frames "
                f"after the burst's {plain['burst']}"
            )

    quiet = read_page(reduced=True)
    if "err" in quiet:
        failures.append(f"reduced: {quiet['err']}")
    else:
        readings.append(
            f"reduced far={quiet['far']}px burst={quiet['burst']} "
            f"grains={quiet['grains']} alive={quiet['alive']}/6"
        )
        if quiet["far"] == 0:
            passed += 1
        else:
            failures.append(f"reduced: the stage still moved {quiet['far']}px")
        if quiet["grains"] == 0:
            passed += 1
        else:
            failures.append(f"reduced: {quiet['grains']} grains were born anyway")
        if quiet["alive"] >= 5:
            passed += 1
        else:
            failures.append(
                f"reduced: the world advanced in {quiet['alive']}/6 frames - "
                "less motion is not a stopped game"
            )
        if quiet["rest"] == quiet["settled"] and quiet["amount"] == 0:
            passed += 1
        else:
            failures.append(f"reduced: the stage left its place ({quiet['settled']})")

    return JuiceOnScreenResult(
        checks_passed=passed,
        checks_total=total,
        failures=tuple(failures[:4]),
        readings=tuple(readings),
    )


__all__ = [
    "ASK",
    "GRAIN_FACTOR",
    "JuiceOnScreenResult",
    "MOVED_PX",
    "WEIGHT",
    "evaluate_juice_reaches_the_screen",
    "read_page",
]
