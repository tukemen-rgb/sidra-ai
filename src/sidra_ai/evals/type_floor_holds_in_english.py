"""Does §24's type floor hold on the pages the product now ships in English?

C-1967. §24's checks have always been run on Japanese pages: the requests
in the collector's own table are all Japanese, so six cycles of putting the
screen into English (C-1959..C-1965) produced pages nothing measured for
type size.

They could not simply be pointed at the existing check, because check (b)
asked ``characters x px > 720``. A character is one em in Japanese and
about 0.6 em in ASCII monospace, so every English page reported a line off
the canvas - 43x22 = 946 "px" for a line that measures 568. C-1967 taught
the probe to measure the width (``drawnWidth``); this eval is what then
became possible.

**The same three checks, on the narrowest glass** (360 CSS px, §24's own
case):

1. Every size a page draws clears the floor in EFFECTIVE pixels.
2. No line is wider than the canvas - measured, not counted.
3. Every word's box is on the glass, top and bottom.

Ten templates, each asked for in English, each measured to actually land
on the template it names.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.hudpaint import textsize_probe
from sidra_ai.evals.drawn_text_stays_on_the_canvas import ENGLISH_ASKS

#: §24 事実 2: iOS Caption 2, the smallest size the platform itself ships.
FLOOR = 11.0

#: The narrowest promoted landscape glass, which is where the floor bites.
CSS_WIDTH = 360

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 320

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)


@dataclass(frozen=True)
class TypeFloorResult:
    templates_ok: int
    templates_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _one(item: tuple[str, str]) -> tuple[str, str]:
    key, ask = item
    made = generate_game(ask)
    if made.template != key:
        return key, f"no English request reaches it (it made a {made.template})"
    found = _SCRIPT.search(made.html)
    if not found:  # pragma: no cover - the page always has one
        return key, "the page carried no script"
    run = subprocess.run(
        ["node", "-"],
        input=textsize_probe(found.group(1), css_w=CSS_WIDTH),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if run.returncode != 0:
        return key, f"the probe did not run: {run.stderr.strip()[-100:]}"
    seen = json.loads(run.stdout.strip().splitlines()[-1])

    rows: dict[str, dict] = {}
    for where in ("title", "played"):
        for name, box in (seen.get(where) or {}).items():
            if name == "?":
                return key, "a word was drawn with no font at all"
            keep = rows.setdefault(name, dict(box))
            keep["longest"] = max(keep["longest"], box["longest"])
            keep["widest"] = max(keep.get("widest", 0), box.get("widest", 0))
            keep["top"] = min(keep["top"], box["top"])
            keep["bottom"] = max(keep["bottom"], box["bottom"])
    if not rows:
        return key, "nothing was written, so nothing is proved"

    small = [
        f"{row['px']:.1f}px→{row['effective']:.2f}"
        for row in rows.values()
        if row["effective"] < FLOOR - 0.01
    ]
    if small:
        return key, f"below the {FLOOR:.0f} floor: {', '.join(small[:3])}"
    wide = [
        f"{row['widest']:.0f}px ({row['longest']} chars at {row['px']:.0f}px)"
        for row in rows.values()
        if row.get("widest", 0) > CANVAS_WIDTH
    ]
    if wide:
        return key, f"wider than the canvas: {wide[0]}"
    off = [
        f"top {row['top']:.1f} / bottom {row['bottom']:.1f}"
        for row in rows.values()
        if row["top"] < -0.01 or row["bottom"] > CANVAS_HEIGHT + 0.01
    ]
    if off:
        return key, f"off the glass: {off[0]}"
    return key, ""


def evaluate_type_floor_holds_in_english() -> TypeFloorResult:
    items = sorted(ENGLISH_ASKS.items())
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return TypeFloorResult(0, len(items), ("node is not installed",))

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(_one, items))

    failures = tuple(f"{key}: {why}" for key, why in outcomes if why)
    ok = sum(1 for _, why in outcomes if not why)
    return TypeFloorResult(
        templates_ok=ok,
        templates_total=len(items),
        failures=failures,
        readings=(f"{len(items)} English pages at {CSS_WIDTH} CSS px",),
    )


__all__ = [
    "CSS_WIDTH",
    "FLOOR",
    "TypeFloorResult",
    "evaluate_type_floor_holds_in_english",
]
