"""Does the page fit 320 CSS pixels without a second direction to scroll?

C-1970, §41 (WCAG 2.2 SC 1.4.10 Reflow, Level AA): content is presented
without loss and without scrolling in two dimensions at a width of 320 CSS
px. The exception covers parts that need a two-dimensional layout - a map,
a video, the game board itself - but not the panel of controls underneath
it, which is ordinary page content.

**Measured in a narrow frame, not a narrow window.** Headless Chromium
will not open a window under about 500px, so asking for
``--window-size=320`` and reading ``clientWidth`` gives 485 and a clean
bill of health that means nothing. The page is loaded inside a 320px
``<iframe>`` instead, which really is a 320px viewport, and the frame's own
document is measured.

**What this counts.** Pages (English and Japanese) whose document is no
wider than its viewport, with the panels open - the state a person is in
when they are using the controls.

The defect this was written for: the English key-settings row
("press a key to change") was 12px wider than the page while the Japanese
one fitted. A translation can push a layout over an edge no test was
watching.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

#: SC 1.4.10's width. The frame is this wide; its document must not be wider.
WIDTH = 320
HEIGHT = 568

ASKS: dict[str, str] = {
    "EN": "make a catching game about an owl",
    "JA": "ふくろうのキャッチゲームを作って",
}

_TITLE = re.compile(r"<title>REFLOW(.*?)</title>", re.S)

_OUTER = """<!doctype html><html><body style="margin:0">
<iframe id="f" src="PAGE_TOKEN" style="width:WIDTH_TOKENpx;height:HEIGHT_TOKENpx;border:0"></iframe>
<script>
addEventListener('load', function(){
  const f = document.getElementById('f');
  /* Open the drawers: a closed panel cannot overflow, and the panel is
     what this is about (C-1969 measured the same trap for target size). */
  setTimeout(function(){
    try { f.contentDocument.querySelectorAll('details').forEach(function(d){ d.open = true }) }
    catch (e) {}
  }, 300);
  setTimeout(function(){
    let out = {};
    try {
      const doc = f.contentDocument, de = doc.documentElement;
      const wide = [];
      doc.querySelectorAll('*').forEach(function(el){
        const r = el.getBoundingClientRect();
        if (r.right > de.clientWidth + 1) {
          wide.push({tag: el.tagName, right: Math.round(r.right),
                     w: Math.round(r.width),
                     t: (el.textContent || '').trim().slice(0, 24)});
        }
      });
      out = {vw: de.clientWidth, scrollW: de.scrollWidth,
             count: wide.length, over: wide.slice(0, 4)};
    } catch (e) { out = {err: String(e).slice(0, 90)} }
    document.title = 'REFLOW' + JSON.stringify(out);
  }, 1200);
});
</script></body></html>"""


@dataclass(frozen=True)
class ReflowResult:
    pages_that_fit: int
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
            .replace("HEIGHT_TOKEN", str(HEIGHT)),
            encoding="utf-8",
        )
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--virtual-time-budget=8000",
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


def evaluate_page_reflows_at_320px() -> ReflowResult:
    failures: list[str] = []
    readings: list[str] = []
    fit = 0

    for label, ask in ASKS.items():
        seen = _measure(generate_game(ask).html)
        if "err" in seen:
            failures.append(f"{label}: {seen['err']}")
            continue
        if seen["scrollW"] > seen["vw"] + 1 or seen["count"]:
            worst = seen["over"][0] if seen["over"] else {}
            failures.append(
                f"{label}: {seen['scrollW']}px of content in a {seen['vw']}px page"
                + (
                    f" ({worst.get('tag', '?').lower()} {worst.get('t', '')!r} "
                    f"reaches {worst.get('right')})"
                    if worst
                    else ""
                )
            )
        else:
            fit += 1
        readings.append(
            f"{label} {seen['scrollW']}/{seen['vw']}px, {seen['count']} past the edge"
        )

    return ReflowResult(
        pages_that_fit=fit,
        pages_total=len(ASKS),
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["HEIGHT", "ReflowResult", "WIDTH", "evaluate_page_reflows_at_320px"]
