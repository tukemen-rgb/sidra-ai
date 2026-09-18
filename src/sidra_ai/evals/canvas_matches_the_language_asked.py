"""How many templates draw their canvas in the language the request was in?

C-1960, after C-1959 did the shared words and ``catch``. The pair judge
(``catch_canvas_matches_the_language_asked``) watches both directions on
one template; this one counts the templates, so the work that is left is a
number rather than a note.

**Every template, not the finished ones.** Counting only the templates a
cycle has already done would be a number that cannot go down and cannot
show a gap. All ten are asked for in English and all ten are counted.

**Read what was drawn** (C-1640): each page is played to the end of a go on
a recording context and every ``fillText`` is written down.

**A request that lands somewhere else fails.** C-1960 measured that no
English phrasing reached ``marble`` at all - "make a marble game" produced
a fishing game - so a translated marble page would have been unreachable.
A judge that only looked at the page it got back would have scored that as
a pass, because the fishing page it was handed was perfectly English.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.hudpaint import text_probe

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
_NUMBER = re.compile(r"[0-9０-９]+")

#: One English request per template, each measured to actually land there.
TEMPLATE_ASKS: dict[str, str] = {
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


@dataclass(frozen=True)
class CanvasLanguageResult:
    templates_in_the_language_asked: int
    templates_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _one(key: str) -> tuple[str, str]:
    """``(key, why it failed)`` - an empty reason means it came out right."""

    made = generate_game(TEMPLATE_ASKS[key])
    if made.template != key:
        return key, f"no English request reaches it (it made a {made.template})"
    found = _SCRIPT.search(made.html)
    if not found:  # pragma: no cover - the page always has one
        return key, "the page carried no script"
    run = subprocess.run(
        ["node", "-"],
        input=text_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if run.returncode != 0:
        return key, f"the page did not run: {run.stderr.strip()[-100:]}"
    data = json.loads(run.stdout.strip().splitlines()[-1])
    shapes = sorted({_NUMBER.sub("N", op["txt"]) for op in data["ops"] if op.get("t") == "t"})
    left = [shape for shape in shapes if _JAPANESE.search(shape)]
    if left:
        return key, f"{len(left)} of {len(shapes)} shapes still Japanese ({left[0]})"
    return key, ""


def evaluate_canvas_matches_the_language_asked() -> CanvasLanguageResult:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return CanvasLanguageResult(0, len(TEMPLATE_ASKS), ("node is not installed",))

    keys = sorted(TEMPLATE_ASKS)
    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        outcomes = list(pool.map(_one, keys))

    failures = tuple(f"{key}: {why}" for key, why in outcomes if why)
    right = sum(1 for _, why in outcomes if not why)
    readings = tuple(f"{key} {'ok' if not why else 'JA'}" for key, why in outcomes)
    return CanvasLanguageResult(right, len(keys), failures, readings)


__all__ = [
    "CanvasLanguageResult",
    "TEMPLATE_ASKS",
    "evaluate_canvas_matches_the_language_asked",
]
