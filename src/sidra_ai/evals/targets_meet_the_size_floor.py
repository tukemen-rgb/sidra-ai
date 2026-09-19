"""Is every pointer target at least 24 x 24 CSS pixels (§40, SC 2.5.8)?

C-1968. WCAG 2.2 SC 2.5.8 Target Size (Minimum) asks for 24 x 24 CSS px on
a pointer target, with five exceptions - of which only **Spacing** applies
here: an undersized target passes when a 24px-diameter circle centred on
it touches no other target's circle.

The page has held a FINGER to 44/48px since C-1712, inside a
``@media (pointer:coarse)`` block. A mouse is a pointer too, and outside
that block the panel's own controls were what the browser gave them: 13x13
checkboxes, 129x16 sliders, a 63x19 select, 146x21 buttons - measured, not
guessed.

**Measured with the drawers open** (C-1969). The panels are ``<details>``
and they start closed; Chromium hides a closed one with
``content-visibility: hidden``, which still answers
``getBoundingClientRect()`` with a box while refusing ``focus()``. So the
first version of this eval measured boxes nobody was looking at. The
numbers happened to be the same once the panels were opened - luck, not
method - and the probe now opens them first.

**Touchable is not enough: it has to be reachable.** A 24px control that
cannot take focus is 24px of nothing to a keyboard. The probe focuses each
one and reports whether it landed. Disabled controls are excluded on
purpose: the locked colours in the looks panel are not operable yet, and
that is what ``disabled`` is for.

**Measured in a real browser.** Two cycles running (C-1966, C-1967) the
defect was in a probe that did not model what a browser does, so this one
does not model anything: it opens the generated page in headless Chromium
at a phone width, reads ``getBoundingClientRect()`` for every interactive
element, and reports what the box really was. No driver is needed - the
page writes its own measurements into ``document.title`` and ``--dump-dom``
brings them back.

**What this counts.** TARGETS that are at least 24 x 24 AND that a
keyboard can reach, over both pages - not pages that pass the standard.

That is stricter than SC 2.5.8, on purpose, and the difference was
measured: before C-1968 the English page had 16 targets under the floor
and the Japanese one 11, but only ONE on each was close enough to another
to fail the Spacing exception. Leaning on that exception means the panel
conforms because of where its rows happen to sit: a longer label, a
reflow, one more control, and the spacing that excused a 13 x 13 checkbox
is gone. The size is the thing the product can hold; the spacing is not.
The spacing is still computed, and the detail says how many were strict
violations, so the standard's own reading stays visible.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game

#: SC 2.5.8's number, and the circle the Spacing exception is measured with.
FLOOR = 24.0

#: A phone-width window, which is where the panel is tightest.
WINDOW = (390, 844)

#: Where Playwright's browsers live in this image. Checked rather than
#: assumed: without it this eval reports that it could not measure, which
#: is not the same as passing.
CHROME = os.environ.get(
    "SIDRA_CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
)

ASKS: dict[str, str] = {
    "EN": "make a catching game about an owl",
    "JA": "ふくろうのキャッチゲームを作って",
}

_TITLE = re.compile(r"<title>MEASURED(.*?)</title>", re.S)

_MEASURE = """
<script>
addEventListener('load', function(){
  /* Open every drawer first: a closed <details> keeps its boxes but
     refuses focus, so measuring it measures a state nobody is in. */
  setTimeout(function(){
    document.querySelectorAll('details').forEach(function(d){ d.open = true });
  }, 200);
  setTimeout(function(){
    const out = [];
    document.querySelectorAll('button, a[href], input, select, summary, [role=button]')
      .forEach(function(el){
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) { return }
        let focusable = false;
        try { el.focus(); focusable = (document.activeElement === el) } catch (e) {}
        out.push({tag: el.tagName, type: el.type || '',
                  t: (el.textContent || '').slice(0, 16),
                  w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10,
                  x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
                  disabled: !!el.disabled, focusable: focusable});
      });
    document.title = 'MEASURED' + JSON.stringify(out);
  }, 900);
});
</script>
"""


@dataclass(frozen=True)
class TargetSizeResult:
    targets_at_the_floor: int
    targets_total: int
    strict_violations: int = 0
    unreachable: int = 0
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _measure(html: str) -> list[dict] | None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return None
    with tempfile.TemporaryDirectory() as room:
        page = pathlib.Path(room) / "page.html"
        page.write_text(html.replace("</body>", _MEASURE + "</body>"), encoding="utf-8")
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                            "--virtual-time-budget=6000",
                f"--window-size={WINDOW[0]},{WINDOW[1]}",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    return json.loads(found.group(1)) if found else None


def _under(items: list[dict]) -> tuple[list[str], list[str]]:
    """``(under the floor, and of those the ones the standard fails too)``."""

    small: list[str] = []
    bad: list[str] = []
    for item in items:
        if item["w"] >= FLOOR and item["h"] >= FLOOR:
            continue
        name = (
            f"{item['tag'].lower()}/{item['type'] or '-'} "
            f"{item['w']}x{item['h']} {item['t'].strip()[:18]!r}"
        )
        small.append(name)
        centre = (item["x"] + item["w"] / 2, item["y"] + item["h"] / 2)
        crowded = any(
            other is not item
            and math.hypot(
                centre[0] - (other["x"] + other["w"] / 2),
                centre[1] - (other["y"] + other["h"] / 2),
            )
            < FLOOR
            for other in items
        )
        if crowded:
            bad.append(name)
    return small, bad


def evaluate_targets_meet_the_size_floor() -> TargetSizeResult:
    failures: list[str] = []
    readings: list[str] = []
    at_floor = 0
    total = 0
    strict = 0
    unreachable = 0

    for label, ask in ASKS.items():
        items = _measure(generate_game(ask).html)
        if items is None:
            failures.append(f"{label}: the page could not be measured (no browser)")
            continue
        if not items:
            failures.append(f"{label}: the page offered nothing to press")
            continue
        small, bad = _under(items)
        total += len(items)
        strict += len(bad)
        cannot = [
            item for item in items
            if not item.get("disabled") and not item.get("focusable")
        ]
        unreachable += len(cannot)
        # A target counts when it meets the floor AND a keyboard can get to
        # it (C-1969). Size alone was a number that did not move when the
        # probe measured a closed drawer - 15 controls out of reach and the
        # count unchanged. Disabled controls are not "out of reach": they
        # are not operable on purpose.
        names_small = set(small)
        counted = 0
        for item in items:
            name = (
                f"{item['tag'].lower()}/{item['type'] or '-'} "
                f"{item['w']}x{item['h']} {item['t'].strip()[:18]!r}"
            )
            if name in names_small:
                continue
            if not item.get("disabled") and not item.get("focusable"):
                continue
            counted += 1
        at_floor += counted
        if cannot:
            failures.append(
                f"{label}: {len(cannot)} control(s) a keyboard cannot reach "
                f"({cannot[0]['tag'].lower()} {cannot[0]['t'].strip()[:18]!r})"
            )
        if small:
            failures.append(
                f"{label}: {len(small)} of {len(items)} under {FLOOR:.0f}px "
                f"({small[0]}){'; ' + str(len(bad)) + ' also fail the spacing exception' if bad else ''}"
            )
        readings.append(
            f"{label} {len(items) - len(small)}/{len(items)} at the floor, "
            f"{len(bad)} strict violations, {len(cannot)} unreachable"
        )

    return TargetSizeResult(
        targets_at_the_floor=at_floor,
        targets_total=total,
        strict_violations=strict,
        unreachable=unreachable,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["FLOOR", "TargetSizeResult", "evaluate_targets_meet_the_size_floor"]
