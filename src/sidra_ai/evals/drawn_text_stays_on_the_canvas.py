"""Does every word the page draws stay on the canvas - in both languages?

C-1966. Six cycles put the screen into the language of the request
(C-1959..C-1965). English says the same thing in more characters than
Japanese does, so the question a translation raises last is a layout one:
does the longer line still fit?

**Width is measured, not counted** (§35). A drawn glyph is one em in
Japanese and about 0.6 em in ASCII monospace, so the character count that
serves for one language is 40% wrong for the other.

**Position needs the drawing state.** Where a word starts depends on
``textAlign``, and ``textAlign`` lives inside a ``save``/``restore`` stack.
A probe without that stack reports a centre alignment leaking into every
later draw - which is exactly the reading C-1966 filed a defect on before
the state was modelled. ``hudpaint.state_probe`` keeps the stack.

**What this counts.** Templates whose every drawn word sits inside the
canvas, over ten templates in each language - twenty pages. It starts full
and can only fall: it is a GUARD, and it exists because the next
translation is the one that pushes a line off the screen.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.hudpaint import drawn_width, state_probe

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
_PX = re.compile(r"([0-9.]+)px")

#: The canvas the pages are built at (games.py's own element).
CANVAS_WIDTH = 720

ENGLISH_ASKS: dict[str, str] = {
    "adventure": "make an adventure game about an owl",
    "catch": "make a catching game about an owl",
    "duel": "make a duel game about an owl",
    "fishing": "make a fishing game about an owl",
    "kaiju": "make a kaiju monster game about an owl",
    "marble": "make a marble game about an owl",
    "platformer": "make a platformer game about an owl",
    "puzzle": "make a puzzle game about an owl",
    "racing": "make a racing game about an owl",
    "shooter": "make a shooting game about an owl",
}

JAPANESE_ASKS: dict[str, str] = {
    "adventure": "ふくろうの冒険ゲームを作って",
    "catch": "ふくろうのキャッチゲームを作って",
    "duel": "ふくろうの対戦ゲームを作って",
    "fishing": "ふくろうの釣りゲームを作って",
    "kaiju": "ふくろうの怪獣ゲームを作って",
    "marble": "ふくろうの玉転がしゲームを作って",
    "platformer": "ふくろうのジャンプアクションゲームを作って",
    "puzzle": "ふくろうのパズルゲームを作って",
    "racing": "ふくろうのレースゲームを作って",
    "shooter": "ふくろうのシューティングゲームを作って",
}


@dataclass(frozen=True)
class OnCanvasResult:
    pages_inside: int
    pages_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _one(job: tuple[str, str, str]) -> tuple[str, str, int]:
    """``(label, why it failed, how many words were drawn)``."""

    label, ask, want = job
    made = generate_game(ask)
    if made.template != want:
        return label, f"the request made a {made.template}, not a {want}", 0
    found = _SCRIPT.search(made.html)
    if not found:  # pragma: no cover - the page always has one
        return label, "the page carried no script", 0
    run = subprocess.run(
        ["node", "-"],
        input=state_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if run.returncode != 0:
        return label, f"the page did not run: {run.stderr.strip()[-100:]}", 0
    ops = json.loads(run.stdout.strip().splitlines()[-1])["ops"]
    for op in ops:
        found_px = _PX.search(op["font"] or "")
        px = float(found_px.group(1)) if found_px else 13.0
        width = drawn_width(op["txt"], px)
        align = op["align"]
        left = op["x"] - (width / 2 if align == "center" else (width if align == "right" else 0))
        if left < 0 or left + width > CANVAS_WIDTH:
            return (
                label,
                f"{op['txt'][:34]!r} runs {round(left)}..{round(left + width)} "
                f"across a {CANVAS_WIDTH}px canvas",
                len(ops),
            )
    return label, "", len(ops)


def evaluate_drawn_text_stays_on_the_canvas() -> OnCanvasResult:
    jobs = [(f"EN {key}", ask, key) for key, ask in sorted(ENGLISH_ASKS.items())]
    jobs += [(f"JA {key}", ask, key) for key, ask in sorted(JAPANESE_ASKS.items())]

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return OnCanvasResult(0, len(jobs), ("node is not installed",))

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(_one, jobs))

    failures = tuple(f"{label}: {why}" for label, why, _ in outcomes if why)
    inside = sum(1 for _, why, _ in outcomes if not why)
    drawn = sum(count for _, _, count in outcomes)
    return OnCanvasResult(
        pages_inside=inside,
        pages_total=len(jobs),
        failures=failures,
        readings=(f"{drawn} drawn words measured across {len(jobs)} pages",),
    )


__all__ = [
    "CANVAS_WIDTH",
    "ENGLISH_ASKS",
    "JAPANESE_ASKS",
    "OnCanvasResult",
    "evaluate_drawn_text_stays_on_the_canvas",
]
