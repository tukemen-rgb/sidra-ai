"""Are the panels under the canvas in the language the request was in?

C-1965. The frame is HTML (C-1956), the game is canvas (C-1959..C-1964),
and between them sit the controls a player actually touches: the key
settings, the looks, the tuning, the copy button, the note saying the
difficulty eased itself. They are built by the page's own JavaScript at
load time, so neither the HTML nor the canvas judges ever saw them.

**Built, not grepped** (C-1640). The page is run on a recording document:
``createElement`` returns a node that remembers, ``appendChild`` builds the
tree, and afterwards the tree is walked. A judge that searched the script
for ``textContent=`` would pass on a panel that is never built; this one
counts what a reader would meet.

**What this counts.** Sides of the pair that come out right, with the
Japanese side as a GUARD rather than half the score (C-1939):

1. Not one Japanese character in everything the English page's panels say.
2. The panels are still there - the same number of them, carrying the same
   number of pieces of text - so "translating" by not building a panel
   fails.
3. The Japanese page still says its own words.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.paneltext import panel_probe

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)

ENGLISH_ASK = "make a catching game about an owl"
JAPANESE_ASK = "ふくろうのキャッチゲームを作って"


@dataclass(frozen=True)
class PanelResult:
    sides_right: int
    sides_total: int
    japanese_held: bool
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _panels(ask: str) -> tuple[dict | None, str]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return None, "node is not installed"
    made = generate_game(ask)
    found = _SCRIPT.search(made.html)
    if not found:  # pragma: no cover - the page always has one
        return None, "the page carried no script"
    run = subprocess.run(
        ["node", "-"],
        input=panel_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if run.returncode != 0:
        return None, f"the page did not run: {run.stderr.strip()[-120:]}"
    return json.loads(run.stdout.strip().splitlines()[-1]), ""


def evaluate_panels_match_the_language_asked() -> PanelResult:
    failures: list[str] = []
    readings: list[str] = []

    japanese, why = _panels(JAPANESE_ASK)
    japanese_right = False
    if japanese is None:
        failures.append(f"Japanese: {why}")
    else:
        drew = [text for text in japanese["texts"] if _JAPANESE.search(text)]
        if not drew:
            failures.append("Japanese: the panels said nothing in Japanese")
        else:
            japanese_right = True
        readings.append(
            f"JA {japanese['built']} panels, {len(japanese['texts'])} texts, "
            f"{len(drew)} Japanese"
        )

    english, why = _panels(ENGLISH_ASK)
    english_right = False
    if english is None:
        failures.append(f"English: {why}")
    else:
        left = [text for text in english["texts"] if _JAPANESE.search(text)]
        thinner = japanese is not None and (
            english["built"] < japanese["built"]
            or len(english["texts"]) < len(japanese["texts"])
        )
        if left:
            failures.append(
                f"English: {len(left)} of the {len(english['texts'])} things the "
                f"panels say are still Japanese ({left[0][:40]})"
            )
        elif thinner:
            failures.append(
                f"English: the panels came out thinner than the Japanese ones "
                f"({english['built']} vs {japanese['built']} panels, "
                f"{len(english['texts'])} vs {len(japanese['texts'])} texts)"
            )
        else:
            english_right = True
        readings.append(
            f"EN {english['built']} panels, {len(english['texts'])} texts, "
            f"{len(left)} Japanese"
        )

    return PanelResult(
        sides_right=int(english_right) + int(japanese_right),
        sides_total=2,
        japanese_held=japanese_right,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = [
    "ENGLISH_ASK",
    "JAPANESE_ASK",
    "PanelResult",
    "evaluate_panels_match_the_language_asked",
]
