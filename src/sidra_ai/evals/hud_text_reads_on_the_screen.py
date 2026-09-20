"""Does the HUD's text clear 4.5:1 where it actually landed?

C-1986, §4 (WCAG 1.4.3). Two judges already watch this:
``creation_hud_contrast`` blends the ink, plate and alpha that
``hudFacts()`` declares and does the arithmetic in Python, and
``creation_hud_painted`` checks a recording context saw those declarations
painted. Together they say the declaration is readable and the page really
paints it.

Neither can say what the eye gets. Anything drawn after the HUD - a burst
of grains, a flash, the touch pad, a scrim - lands on the same pixels
without changing a single declared value.

So this reads the composited frame: the ink's own pixels are found by the
colour ``hudFacts()`` names, their surroundings are sampled where the text
is not, and the WCAG ratio is computed between the two.

**Why the median, and only the median.** A letter sits on a plate that sits
on a sky, and the sky moves; one sample would be the lamp, not the plate.
And the pixels closest to a letter are the letter: text is anti-aliased
into its background, so any "worst pixel" statistic reads the glyph's own
edge. Measured while building this - a 90th percentile read 1.5:1 on three
of four templates, all of it antialiasing. The median of the pixels within
six of an ink pixel is the backdrop the letters are read against.
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

#: Four templates whose HUDs sit on different kinds of backdrop: a sky, a
#: lit cave, a board, a road.
ASKS: dict[str, str] = {
    "catch": "ふくろうのキャッチゲームを作って",
    "adventure": "ふくろうの冒険ゲームを作って",
    "puzzle": "ふくろうのパズルゲームを作って",
    "racing": "ふくろうのレースゲームを作って",
}

#: §4 / WCAG 1.4.3 for body-sized text.
FLOOR = 4.5

_TITLE = re.compile(r"<title>HUDREAD(.*?)</title>", re.S)

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
      step(90);
      const cv = document.querySelector('canvas');
      const cx = cv.getContext('2d');
      const facts = hudFacts();
      out.ink = facts.ink;
      const hex = String(facts.ink).replace('#', '');
      const want = [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16),
                    parseInt(hex.slice(4, 6), 16)];
      const lin = function(v){ v /= 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) };
      const lum = function(r, g, b){ return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b) };
      const d = cx.getImageData(0, 0, cv.width, cv.height).data;
      /* Every pixel the ink itself wrote, and which rows it wrote on. */
      const rows = {};
      let inkN = 0;
      for (let y = 0; y < cv.height; y++) {
        for (let x = 0; x < cv.width; x++) {
          const i = (y * cv.width + x) * 4;
          if (d[i] === want[0] && d[i + 1] === want[1] && d[i + 2] === want[2]) {
            inkN++; (rows[y] = rows[y] || []).push(x) } } }
      out.inkPixels = inkN;
      if (!inkN) { document.title = 'HUDREAD' + JSON.stringify(out); return }
      /* The backdrop each letter actually sits on: within six pixels of an
         ink pixel, on its own row. Taking the whole row's span instead
         reached past the plate and into the world - measured, and it made
         catch's worst reading 1.97:1 against a plate that is not there. */
      const back = [];
      Object.keys(rows).forEach(function(key){
        const y = +key, xs = rows[key], taken = {};
        xs.forEach(function(x0){
          for (let x = Math.max(0, x0 - 6); x <= Math.min(cv.width - 1, x0 + 6); x++) {
            if (taken[x]) continue;
            const i = (y * cv.width + x) * 4;
            if (d[i] === want[0] && d[i + 1] === want[1] && d[i + 2] === want[2]) continue;
            taken[x] = 1;
            back.push(lum(d[i], d[i + 1], d[i + 2])) } }) });
      back.sort(function(a, b){ return a - b });
      const plate = back.length ? back[(back.length / 2) | 0] : null;
      const text = lum(want[0], want[1], want[2]);
      out.backSamples = back.length;
      out.plateLum = plate === null ? null : +plate.toFixed(4);
      out.textLum = +text.toFixed(4);
      out.ratio = plate === null ? null
        : +(((Math.max(text, plate) + 0.05) / (Math.min(text, plate) + 0.05))).toFixed(2);
      /* No percentile beyond the median: a letter's own edge is
         anti-aliased into the plate, so the pixels nearest the ink are
         part ink. Measured - the 90th percentile read 1.5:1 on three of
         four templates, which is the edge of the glyph, not a thin
         plate. The median is the plate. */
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'HUDREAD' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class HudReadResult:
    templates_that_read: int
    templates_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def read_template(key: str) -> dict:
    """Composite the page for real and read the ink where it landed."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    html = generate_game(ASKS[key]).html
    body = with_probe_keys(_REPORT)
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
    seen = json.loads(found.group(1)) if found else {"err": "the page said nothing"}
    seen["template"] = key
    return seen


def evaluate_hud_text_reads_on_the_screen() -> HudReadResult:
    keys = sorted(ASKS)
    total = len(keys)
    passed = 0
    failures: list[str] = []
    readings: list[str] = []

    for key in keys:
        seen = read_template(key)
        if "err" in seen:
            failures.append(f"{key}: {seen['err']}")
            continue
        if not seen.get("inkPixels"):
            failures.append(f"{key}: the HUD ink never reached the screen")
            continue
        readings.append(
            f"{key} {seen['ratio']}:1 on {seen['inkPixels']}px of ink"
        )
        if seen["ratio"] is not None and seen["ratio"] >= FLOOR:
            passed += 1
        else:
            failures.append(f"{key}: the ink reads {seen['ratio']}:1 where it landed")

    return HudReadResult(passed, total, tuple(failures[:3]), tuple(readings))


__all__ = [
    "ASKS",
    "FLOOR",
    "HudReadResult",
    "evaluate_hud_text_reads_on_the_screen",
    "read_template",
]
