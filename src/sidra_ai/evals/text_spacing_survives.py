"""Does the page survive a reader's own text spacing (§42, SC 1.4.12)?

C-1971. WCAG 2.2 SC 1.4.12 asks that setting all four of line height 1.5x,
paragraph spacing 2x, letter spacing 0.12x and word spacing 0.16x - and
changing nothing else - costs no content and no functionality. The usual
way to fail it is a compact panel: a row sized for the text it shipped
with, which clips or overflows once a reader spreads the letters out.

This page passes as it stands. The eval exists as a LOCK, not as a repair:
the panel is compact by design (13px type, tight padding), and the next
cycle that tightens a row is the one that would break this without anyone
noticing.

**Measured in a 320px frame**, the width §41 (SC 1.4.10) fixes the page at,
with the drawers open - a closed panel cannot overflow, and the panel is
the thing at risk. The four properties are applied to the page after it
loads, exactly as the criterion describes, and then:

1. Nothing sticks out past the viewport.
2. Nothing that hides its overflow has more content than it can show.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.page_reflows_at_320px import HEIGHT, WIDTH
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

#: The criterion's own four numbers, as a stylesheet the page never had.
SPACING_CSS = (
    "*{line-height:1.5 !important;letter-spacing:0.12em !important;"
    "word-spacing:0.16em !important}p{margin-bottom:2em !important}"
)

ASKS: dict[str, str] = {
    "EN": "make a catching game about an owl",
    "JA": "ふくろうのキャッチゲームを作って",
}

_TITLE = re.compile(r"<title>SPACING(.*?)</title>", re.S)

_OUTER = """<!doctype html><html><body style="margin:0">
<iframe id="f" src="PAGE_TOKEN" style="width:WIDTH_TOKENpx;height:HEIGHT_TOKENpx;border:0"></iframe>
<script>
addEventListener('load', function(){
  const f = document.getElementById('f');
  setTimeout(function(){
    try {
      const doc = f.contentDocument;
      doc.querySelectorAll('details').forEach(function(d){ d.open = true });
      const sheet = doc.createElement('style');
      sheet.textContent = SPACING_TOKEN;
      doc.head.appendChild(sheet);
    } catch (e) {}
  }, 300);
  setTimeout(function(){
    let out = {};
    try {
      const doc = f.contentDocument, de = doc.documentElement;
      const over = [], clipped = [];
      doc.querySelectorAll('*').forEach(function(el){
        const r = el.getBoundingClientRect();
        if (r.right > de.clientWidth + 1) {
          over.push({tag: el.tagName, right: Math.round(r.right),
                     t: (el.textContent || '').trim().slice(0, 22)});
        }
        const cs = getComputedStyle(el);
        if ((cs.overflow === 'hidden' || cs.overflowY === 'hidden')
            && el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1) {
          clipped.push({tag: el.tagName, need: el.scrollHeight, has: el.clientHeight,
                        t: (el.textContent || '').trim().slice(0, 22)});
        }
      });
      out = {vw: de.clientWidth, scrollW: de.scrollWidth,
             over: over.slice(0, 3), overCount: over.length,
             clipped: clipped.slice(0, 3), clippedCount: clipped.length};
    } catch (e) { out = {err: String(e).slice(0, 90)} }
    document.title = 'SPACING' + JSON.stringify(out);
  }, 1300);
});
</script></body></html>"""


@dataclass(frozen=True)
class TextSpacingResult:
    pages_that_hold: int
    pages_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _measure(html: str) -> dict:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    with tempfile.TemporaryDirectory() as room:
        inner = pathlib.Path(room) / "page.html"
        inner.write_text(html, encoding="utf-8")
        outer = pathlib.Path(room) / "frame.html"
        outer.write_text(
            _OUTER.replace("PAGE_TOKEN", inner.name)
            .replace("WIDTH_TOKEN", str(WIDTH))
            .replace("HEIGHT_TOKEN", str(HEIGHT))
            .replace("SPACING_TOKEN", json.dumps(SPACING_CSS)),
            encoding="utf-8",
        )
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--virtual-time-budget=9000",
                "--window-size=900,700",
                "--dump-dom",
                f"file://{outer}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    return json.loads(found.group(1)) if found else {"err": "the frame said nothing"}


def evaluate_text_spacing_survives() -> TextSpacingResult:
    failures: list[str] = []
    readings: list[str] = []
    held = 0

    for label, ask in ASKS.items():
        seen = _measure(generate_game(ask).html)
        if "err" in seen:
            failures.append(f"{label}: {seen['err']}")
            continue
        if seen["overCount"]:
            worst = seen["over"][0]
            failures.append(
                f"{label}: {seen['overCount']} past the edge with the reader's "
                f"spacing ({worst['tag'].lower()} {worst['t']!r} reaches {worst['right']})"
            )
        elif seen["clippedCount"]:
            worst = seen["clipped"][0]
            failures.append(
                f"{label}: {seen['clippedCount']} clipped ({worst['tag'].lower()} "
                f"needs {worst['need']}px in {worst['has']}px)"
            )
        else:
            held += 1
        readings.append(
            f"{label} {seen['scrollW']}/{seen['vw']}px, {seen['overCount']} past the "
            f"edge, {seen['clippedCount']} clipped"
        )

    return TextSpacingResult(
        pages_that_hold=held,
        pages_total=len(ASKS),
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["SPACING_CSS", "TextSpacingResult", "evaluate_text_spacing_survives"]
