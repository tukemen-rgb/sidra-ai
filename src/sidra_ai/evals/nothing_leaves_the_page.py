"""Does the page talk to anyone, when a real browser opens it?

C-1983, §9. SIDRA's position against the market's three complaints rests
on one promise a reader can check: the page is a single file that sends
nothing anywhere.

``creation_page_is_self_contained`` already tests that behaviourally - but
in node, where ``fetch``, ``XMLHttpRequest``, ``WebSocket``,
``EventSource`` and ``sendBeacon`` are replaced with throwing stubs. node
has no DOM, so the paths a *browser* walks on its own - ``<img src>``, a
CSS ``url(...)``, a web font, ``/favicon.ico`` - go through none of those
stubs. And a spelling scan for ``://`` cannot see a relative request.

So this reads Chromium's own record of its traffic (``--log-net-log``)
while the page is opened and played.

**The browser talks for itself.** Even a blank page draws four requests in
this build (a time service, ListAccounts, google.com, an async fetch), and
no flag removed them. So the reading is a difference: the same browser
opens a control page that paints one rectangle, and the product page must
add nothing to what the control asked for. The page's own ``file://`` URL
is excluded; any *other* ``file://`` is counted, because that is what a
stray relative asset would look like.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.canvas_matches_the_language_asked import TEMPLATE_ASKS
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

#: A page that paints and nothing else: the floor for what this browser
#: asks for on its own.
CONTROL = (
    "<!doctype html><html><head><title>control</title></head><body>"
    '<canvas width="720" height="320"></canvas><script>'
    "document.querySelector('canvas').getContext('2d').fillRect(0,0,40,40);"
    "</script></body></html>"
)

#: Everything that keeps the browser's own errands down. They do not remove
#: them (measured), which is why the reading is a difference.
QUIET = (
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=OptimizationHints,MediaRouter,Translate",
)

_URL = re.compile(r'"url":"([^"]+)"')

#: The browser stamps a fresh nonce into its own time-service query every
#: run, so the comparison is by scheme, host and path. A page that reached
#: for a host nobody asked for still shows; a query string is not where a
#: leak hides. ``data:`` and ``blob:`` are not traffic - the favicon is a
#: data: URI, by C-1218's design - so they are left out.
def _place(url: str) -> str | None:
    if url.startswith(("data:", "blob:")):
        return None
    return url.split("?", 1)[0].split("#", 1)[0]

#: Opens the game, turns 200 real frames of its loop and touches it once,
#: so anything sent while playing lands in the record too.
_DRIVE = """
<script>
window.__q = [];
window.requestAnimationFrame = function(fn){ window.__q.push(fn); return window.__q.length };
</script>
"""

_PLAY = """
<script>
addEventListener('load', function(){
  setTimeout(function(){
    try {
      let T = 0;
      const step = function(n){
        for (let k = 0; k < n && window.__q.length; k++) {
          const due = window.__q; window.__q = []; T += 16;
          due.forEach(function(fn){ fn(T) }) } };
      step(4);
      const cv = document.querySelector('canvas');
      const r = cv.getBoundingClientRect();
      ['pointerdown', 'pointerup'].forEach(function(type){
        cv.dispatchEvent(new PointerEvent(type, {clientX: r.left + r.width / 2,
          clientY: r.top + r.height / 2, pointerType: 'touch', pointerId: 1,
          isPrimary: true, bubbles: true, cancelable: true})) });
      step(200);
      document.title = 'QUIET' + step.length;
    } catch (e) { document.title = 'QUIETERR' + String(e).slice(0, 60) }
  }, 600);
});
</script>
"""


@dataclass(frozen=True)
class QuietResult:
    templates_that_say_nothing: int
    templates_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _urls(html: str, *, drive: bool) -> set[str] | None:
    """Every URL this browser asked for while showing the page."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return None
    with tempfile.TemporaryDirectory() as room:
        page = pathlib.Path(room) / "page.html"
        body = (
            html.replace("<body", _DRIVE + "<body", 1).replace("</body>", _PLAY + "</body>")
            if drive
            else html
        )
        page.write_text(body, encoding="utf-8")
        log = pathlib.Path(room) / "net.json"
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                *QUIET,
                "--virtual-time-budget=6000",
                "--window-size=390,844",
                f"--log-net-log={log}",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        mine = f"file://{page}"
        return {
            place
            for place in (_place(u) for u in _URL.findall(text) if not u.startswith(mine))
            if place is not None
        }


def evaluate_nothing_leaves_the_page() -> QuietResult:
    keys = sorted(TEMPLATE_ASKS)
    total = len(keys)
    floor = _urls(CONTROL, drive=False)
    if floor is None:
        return QuietResult(0, total, ("no browser",))

    passed = 0
    failures: list[str] = []
    for key in keys:
        seen = _urls(generate_game(TEMPLATE_ASKS[key]).html, drive=True)
        if seen is None:  # pragma: no cover - environment guard
            failures.append(f"{key}: no browser")
            continue
        extra = sorted(seen - floor)
        if not extra:
            passed += 1
        else:
            failures.append(f"{key}: the page reached for {extra[0][:70]}")
    readings = (
        f"{passed}/{total} templates added nothing to the browser's own "
        f"{len(floor)} errands",
    )
    return QuietResult(
        templates_that_say_nothing=passed,
        templates_total=total,
        failures=tuple(failures[:3]),
        readings=readings,
    )


__all__ = [
    "CONTROL",
    "QUIET",
    "QuietResult",
    "evaluate_nothing_leaves_the_page",
]
