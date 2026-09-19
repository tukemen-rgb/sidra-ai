"""Does the artifact remember, and does it know when to stop remembering?

C-1973. A SIDRA game is a file somebody opens. Two promises ride on that:

* **It remembers.** The start screen's three lines are shown once; the next
  time the same page is opened they are skipped (C-1111), which only works
  if ``localStorage`` really works from ``file://``.
* **It stops remembering when the words change.** What is stored is a
  fingerprint of the lines that were actually read (C-1738), so a briefing
  that changed - a new lap count, or the whole thing in another language
  after C-1957 - is news exactly once more.

**Why this needs a real browser.** Every probe in this repository replaces
``localStorage`` with a stub, so the boundary between the page and the
browser's storage has never been measured. A page that wrote to
``sessionStorage``, or under a key that changed every load, would pass every
existing judge and forget everything a person did.

Three checks, in one Chromium profile so the second and third opens see
what the first one left:

1. The first open shows the gate and writes the fingerprint.
2. Opening the same page again skips it.
3. Opening the OTHER language's page does not skip it.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import with_probe_keys
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

JAPANESE_ASK = "ふくろうのキャッチゲームを作って"
ENGLISH_ASK = "make a catching game about an owl"

#: The key the start screen keeps its fingerprint under, for this template.
SEEN_KEY = "sidra.seen.catch"

_TITLE = re.compile(r"<title>GATEMEM(.*?)</title>", re.S)

_REPORT = """
<script>
PROBE_KEYS_PLACEHOLDER
addEventListener('load', function(){
  setTimeout(function(){
    if (PRESS_TOKEN) {
      /* The pair comes from probekeys, not from here (C-1651's ratchet):
         a probe that writes {key:' ', code:' '} by hand presses a key no
         template is listening for, and every gate sits untouched. */
      const pair = probeKey(' ');
      ['keydown', 'keyup'].forEach(function(type){
        const e = new KeyboardEvent(type, {key: pair.key, code: pair.code, bubbles: true});
        document.dispatchEvent(e); window.dispatchEvent(e);
      });
    }
  }, 500);
  setTimeout(function(){
    let out = {};
    try {
      out.skipped = (typeof gateSkipped === 'function') ? !!gateSkipped() : null;
      out.state = (typeof gateState === 'function') ? String(gateState()) : null;
      out.seen = localStorage.getItem('SEEN_KEY_TOKEN');
    } catch (e) { out = {err: String(e).slice(0, 80)} }
    document.title = 'GATEMEM' + JSON.stringify(out);
  }, 1500);
});
</script>
"""


@dataclass(frozen=True)
class GateMemoryResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _open(profile: pathlib.Path, room: pathlib.Path, html: str, name: str, press: bool) -> dict:
    page = room / f"{name}.html"
    page.write_text(
        html.replace(
            "</body>",
            with_probe_keys(
                _REPORT.replace("PRESS_TOKEN", "true" if press else "false").replace(
                    "SEEN_KEY_TOKEN", SEEN_KEY
                )
            )
            + "</body>",
        ),
        encoding="utf-8",
    )
    run = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=6000",
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


def evaluate_gate_memory_survives_a_reopen() -> GateMemoryResult:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return GateMemoryResult(0, 3, ("no browser to measure with",))

    japanese = generate_game(JAPANESE_ASK).html
    english = generate_game(ENGLISH_ASK).html

    failures: list[str] = []
    readings: list[str] = []
    passed = 0

    with tempfile.TemporaryDirectory() as where:
        room = pathlib.Path(where)
        profile = room / "profile"
        shutil.rmtree(profile, ignore_errors=True)

        first = _open(profile, room, japanese, "ja", True)
        if first.get("err"):
            failures.append(f"first open: {first['err']}")
        elif first.get("skipped") is not False or not first.get("seen"):
            failures.append(
                f"first open: skipped={first.get('skipped')!r}, "
                f"stored={first.get('seen')!r} - the gate must be shown and remembered"
            )
        else:
            passed += 1
        readings.append(
            f"1st JA skipped={first.get('skipped')} state={first.get('state')} "
            f"stored={'yes' if first.get('seen') else 'no'}"
        )

        again = _open(profile, room, japanese, "ja", False)
        if again.get("skipped") is True:
            passed += 1
        else:
            failures.append(
                f"reopen: skipped={again.get('skipped')!r} - the same three lines "
                f"were read already"
            )
        readings.append(f"2nd JA skipped={again.get('skipped')}")

        other = _open(profile, room, english, "en", False)
        if other.get("skipped") is False:
            passed += 1
        else:
            failures.append(
                f"other language: skipped={other.get('skipped')!r} - these three "
                f"lines have never been read"
            )
        readings.append(f"EN skipped={other.get('skipped')} state={other.get('state')}")

    return GateMemoryResult(
        checks_passed=passed,
        checks_total=3,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = [
    "ENGLISH_ASK",
    "GateMemoryResult",
    "JAPANESE_ASK",
    "SEEN_KEY",
    "evaluate_gate_memory_survives_a_reopen",
]
