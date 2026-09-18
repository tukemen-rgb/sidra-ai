"""Does the canvas draw in the language the request was in?

C-1959. C-1956 put the page's frame into the language asked and C-1957 the
start screen's three lines; the canvas - the part a player looks at for the
whole of a go - kept drawing Japanese whatever was asked.

**Read what was drawn, not what was declared** (C-1640). The page is run to
the end of a go on a recording context and every ``fillText`` is written
down. A judge that read ``CANVAS_WORDS`` would pass on a page that never
names ``CW``; a judge that read the page's source would pass on a word that
is in the table but never drawn.

**What this counts.** Sides of the pair that come out right, with the
Japanese side as a GUARD rather than half the score (C-1939):

1. Not one Japanese character among everything the English page draws.
2. The English page still draws its HUD - the three words ``catch`` counts
   with - so "translating" by drawing nothing fails.
3. The Japanese page still draws its own words, unchanged in kind.

``catch`` is the template measured: one go of it draws eight distinct
shapes, five of which come from the shared round module and are on every
template. The nine other templates keep their own HUD lines, which are a
separate item; this judge would fail the moment one of them was asked for
in English, so it names the one it drives.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.hudpaint import text_probe

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
_NUMBER = re.compile(r"[0-9０-９]+")

ENGLISH_ASK = "make a catching game about an owl"
JAPANESE_ASK = "ふくろうのキャッチゲームを作って"

#: What the English HUD has to still say. The words come from the table the
#: page is built from, so a rename moves this with it rather than leaving a
#: judge asking for a word nobody draws any more.
from sidra_ai.creation.canvaswords import CANVAS_WORDS  # noqa: E402

_HUD_KEYS = ("score", "caught", "missed")


@dataclass(frozen=True)
class CanvasResult:
    sides_right: int
    sides_total: int
    japanese_held: bool
    failures: tuple[str, ...]
    readings: tuple[str, ...]


def _drawn(ask: str) -> tuple[str, list[str] | None, str]:
    """Every distinct shape the canvas drew for one request."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return "", None, "node is not installed"
    made = generate_game(ask)
    found = _SCRIPT.search(made.html)
    if not found:  # pragma: no cover - the page always has one
        return made.template, None, "the page carried no script"
    run = subprocess.run(
        ["node", "-"],
        input=text_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if run.returncode != 0:
        return made.template, None, f"the page did not run: {run.stderr.strip()[-120:]}"
    data = json.loads(run.stdout.strip().splitlines()[-1])
    shapes = sorted({_NUMBER.sub("N", op["txt"]) for op in data["ops"] if op.get("t") == "t"})
    return made.template, shapes, ""


def evaluate_catch_canvas_matches_the_language_asked() -> CanvasResult:
    failures: list[str] = []
    readings: list[str] = []

    template, english, why = _drawn(ENGLISH_ASK)
    english_right = False
    if english is None:
        failures.append(f"English: {why}")
    elif template != "catch":
        failures.append(f"English: the request made a {template}, not a catch game")
    else:
        japanese_left = [shape for shape in english if _JAPANESE.search(shape)]
        hud = [
            CANVAS_WORDS[key][1]
            for key in _HUD_KEYS
            if not any(CANVAS_WORDS[key][1] in shape for shape in english)
        ]
        if japanese_left:
            failures.append(
                f"English: {len(japanese_left)} of the {len(english)} shapes the canvas "
                f"drew are still Japanese ({japanese_left[0]})"
            )
        elif hud:
            failures.append(f"English: the HUD no longer says {hud}")
        else:
            english_right = True
        readings.append(f"EN {len(english)} shapes, {len(japanese_left)} Japanese")

    _, japanese, why = _drawn(JAPANESE_ASK)
    japanese_right = False
    if japanese is None:
        failures.append(f"Japanese: {why}")
    else:
        drew = [shape for shape in japanese if _JAPANESE.search(shape)]
        if not drew:
            failures.append("Japanese: the canvas drew no Japanese at all")
        else:
            japanese_right = True
        readings.append(f"JA {len(japanese)} shapes, {len(drew)} Japanese")

    return CanvasResult(
        sides_right=int(english_right) + int(japanese_right),
        sides_total=2,
        japanese_held=japanese_right,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = [
    "CanvasResult",
    "ENGLISH_ASK",
    "JAPANESE_ASK",
    "evaluate_catch_canvas_matches_the_language_asked",
]
