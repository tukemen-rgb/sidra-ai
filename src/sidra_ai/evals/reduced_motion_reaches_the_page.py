"""Does the operating system's "reduce motion" actually reach the page?

C-1972. The page promises that motion can be turned down, and the switch in
its own panel is only half of that promise: the other half is
``prefers-reduced-motion``, which a person sets once for their whole
machine and expects every page to obey.

**Why this needs a real browser.** Every probe in this repository replaces
``matchMedia`` - ``globalThis.matchMedia = () => ({matches: false})`` in
games.py, ``(q) => ({matches: REDUCED_INPUT})`` in juice.py. That is the
right thing for a probe that wants to drive both states on demand, and it
means no probe can see whether the page really asks the browser the right
question. Mistype the query and every one of them still passes.

So this opens the same page twice in headless Chromium - once plainly, once
with ``--force-prefers-reduced-motion`` - and reads two things the page
itself computes:

1. ``matchMedia('(prefers-reduced-motion: reduce)').matches``, which is the
   browser's answer, and
2. ``REDUCED``, which is what the page decided from it.

Both must be false when nothing is forced and true when it is. A page that
answered ``true`` either way would be ignoring the person who wants motion;
one that answered ``false`` either way would be ignoring the person who
asked for less.
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

ASK = "ふくろうのキャッチゲームを作って"

#: Chromium's own switch for the setting, so no driver is needed.
FORCE_FLAG = "--force-prefers-reduced-motion"

_TITLE = re.compile(r"<title>REDUCEDMOTION(.*?)</title>", re.S)

_REPORT = """
<script>
addEventListener('load', function(){
  setTimeout(function(){
    let out = {};
    try {
      out.media = matchMedia('(prefers-reduced-motion: reduce)').matches;
      out.reduced = (typeof REDUCED !== 'undefined') ? !!REDUCED : null;
    } catch (e) { out = {err: String(e).slice(0, 80)} }
    document.title = 'REDUCEDMOTION' + JSON.stringify(out);
  }, 1200);
});
</script>
"""


@dataclass(frozen=True)
class ReducedMotionResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _read(html: str, forced: bool) -> dict:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    with tempfile.TemporaryDirectory() as room:
        page = pathlib.Path(room) / "page.html"
        page.write_text(html.replace("</body>", _REPORT + "</body>"), encoding="utf-8")
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--virtual-time-budget=6000",
                "--window-size=390,844",
                *([FORCE_FLAG] if forced else []),
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    return json.loads(found.group(1)) if found else {"err": "the page said nothing"}


def evaluate_reduced_motion_reaches_the_page() -> ReducedMotionResult:
    html = generate_game(ASK).html
    failures: list[str] = []
    readings: list[str] = []
    passed = 0
    total = 4

    for forced in (False, True):
        seen = _read(html, forced)
        where = "forced" if forced else "plain"
        if "err" in seen:
            failures.append(f"{where}: {seen['err']}")
            continue
        for name in ("media", "reduced"):
            got = seen.get(name)
            if got is forced:
                passed += 1
            else:
                failures.append(
                    f"{where}: the page's {name} is {got!r}, expected {forced!r}"
                )
        readings.append(f"{where} media={seen.get('media')} REDUCED={seen.get('reduced')}")

    return ReducedMotionResult(
        checks_passed=passed,
        checks_total=total,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["ASK", "FORCE_FLAG", "ReducedMotionResult", "evaluate_reduced_motion_reaches_the_page"]
