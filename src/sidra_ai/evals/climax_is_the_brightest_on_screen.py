"""Is the climax really the brightest thing the player sees?

C-1978, §7 観察 6 with §43's step. The palette work (C-1036, C-1690, C-1704)
promises that each act repaints the world and that the brightest values are
saved for last. Every judge of that promise so far has read the *ledger* -
``sceneFacts()``, which reports the colours the page passes to ``fillStyle``.

A screen is not a ledger. Tiles, sky, HUD plates, scrims and particles land
on top of the scene colour, and they decide how much of the promise reaches
an eye. So this opens each template in real headless Chromium and reads the
canvas itself:

* ``requestAnimationFrame`` is taken over before the page's own scripts run,
  so the real loop can be stepped 120 frames on demand. (Headless virtual
  time does not drive rAF - measured in C-1973 - and taking it over is how
  that wall is crossed.)
* ``setScene`` is pinned to one act at a time, so the same live world is
  painted in each act's palette.
* ``getImageData`` gives the pixels, and the mean relative luminance of the
  frame is the brightness of that act. Five samples per act, median taken,
  with ``--force-prefers-reduced-motion`` so a flash or a burst does not
  decide the reading.

The bar is §43's: the clinical step for contrast is 0.15 log units (the
Pelli-Robson chart's 1/sqrt(2) between triplets). A climax that beats the
brightest earlier act by less than that is not a peak anyone can see.
"""

from __future__ import annotations

import concurrent.futures
import json
import math
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import with_probe_keys
from sidra_ai.evals.canvas_matches_the_language_asked import TEMPLATE_ASKS
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

#: Frames of the real loop to run before reading. Long enough for kaiju to
#: finish waking (its scrim hides the world until frame ~95), short enough
#: that duel's match has not ended (its own scrim lands around frame 250).
FRAMES = 120

#: Samples per act, median taken: one frame can carry a flash or a spawn.
SAMPLES = 5

#: §43: the step clinical practice treats as one increment of contrast.
STEP_LOG = 0.15

_TITLE = re.compile(r"<title>CLIMAX(.*?)</title>", re.S)

#: Takes the frame clock before the page's scripts run, so the loop can be
#: stepped. The page's own code is untouched - it asks for a frame and gets
#: one, just not from the compositor.
_HOOK = """
<script>
window.__next = null;
window.requestAnimationFrame = function(fn){ window.__next = fn; return 1 };
</script>
"""

_REPORT = """
<script>
PROBE_KEYS_PLACEHOLDER
addEventListener('load', function(){
  setTimeout(function(){
    const out = {painted: [], claim: []};
    try {
      const step = function(n){
        for (let k = 0; k < n && window.__next; k++) {
          const fn = window.__next; window.__next = null; fn(k * 16 + performance.now()) } };
      step(4);
      /* The pair comes from probekeys, not from here (C-1651's ratchet). */
      const pair = probeKey(' ');
      ['keydown', 'keyup'].forEach(function(type){
        const e = new KeyboardEvent(type, {key: pair.key, code: pair.code, bubbles: true});
        document.dispatchEvent(e); window.dispatchEvent(e); });
      step(FRAMES_TOKEN);
      const canvas = document.querySelector('canvas');
      const cx = canvas.getContext('2d');
      const facts = sceneFacts();
      out.claim = facts.scenes.map(function(s){ return +s.lum.toFixed(4) });
      const paint = setScene;
      for (let act = 0; act < facts.scenes.length; act++) {
        /* The page sets the act itself, every frame, from its own progress.
           Pinning its own setter keeps the world live and the palette held. */
        window.setScene = function(){ paint(act) };
        paint(act);
        const takes = [];
        for (let s = 0; s < SAMPLES_TOKEN; s++) {
          step(3);
          const d = cx.getImageData(0, 0, canvas.width, canvas.height).data;
          let lum = 0;
          const lin = function(v){ v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) };
          for (let q = 0; q < d.length; q += 4) {
            lum += 0.2126 * lin(d[q]) + 0.7152 * lin(d[q + 1]) + 0.0722 * lin(d[q + 2]) }
          takes.push(lum / (d.length / 4));
        }
        takes.sort(function(a, b){ return a - b });
        out.painted.push(+takes[(SAMPLES_TOKEN / 2) | 0].toFixed(4));
      }
      window.setScene = paint;
      out.size = [canvas.width, canvas.height];
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'CLIMAX' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class ClimaxResult:
    templates_whose_climax_reads: int
    templates_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _read(html: str) -> dict:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    body = with_probe_keys(
        _REPORT.replace("FRAMES_TOKEN", str(FRAMES)).replace("SAMPLES_TOKEN", str(SAMPLES))
    )
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


def measure(key: str) -> dict:
    """What one template's acts actually paint, in order."""

    seen = _read(generate_game(TEMPLATE_ASKS[key]).html)
    seen["template"] = key
    return seen


def step_of(painted: list[float]) -> float:
    """How far the last act rises above the brightest act before it, in log units."""

    before = max(painted[:-1])
    if before <= 0 or painted[-1] <= 0:
        return 0.0
    return math.log10(painted[-1] / before)


def evaluate_climax_is_the_brightest_on_screen() -> ClimaxResult:
    keys = sorted(TEMPLATE_ASKS)
    total = len(keys)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        seen = list(pool.map(measure, keys))

    passed = 0
    failures: list[str] = []
    readings: list[str] = []
    for row in seen:
        key = row["template"]
        if "err" in row:
            failures.append(f"{key}: {row['err']}")
            continue
        painted = row.get("painted") or []
        if len(painted) < 2:
            failures.append(f"{key}: {len(painted)} act(s) painted")
            continue
        rise = step_of(painted)
        readings.append(f"{key} {painted} {rise:+.3f} log")
        if painted[-1] != max(painted):
            failures.append(f"{key}: the brightest act on screen is not the last ({painted})")
        elif rise < STEP_LOG:
            failures.append(
                f"{key}: the climax rises {rise:+.3f} log, under the {STEP_LOG} step"
            )
        else:
            passed += 1
    return ClimaxResult(
        templates_whose_climax_reads=passed,
        templates_total=total,
        failures=tuple(failures[:4]),
        readings=tuple(sorted(readings)),
    )


__all__ = [
    "FRAMES",
    "SAMPLES",
    "STEP_LOG",
    "ClimaxResult",
    "evaluate_climax_is_the_brightest_on_screen",
    "measure",
    "step_of",
]
