"""Does the game's touch hint name exactly the buttons the pad draws?

C-1287: the hint was the constant 「◀ ▶ / A」 on every template, but the pad
draws only the keys the game reads (PAD_ACTIVE, C-1244) - fishing has no arrows,
racing has no A, a puzzle has ▲▼ the constant never named. So a mobile player was
told about buttons that were not there and not told about ones that were. The
hint is now built from the same PAD_ACTIVE the pad draws from.

The checks generate real games across templates and compare, per page, the glyph
set named in the hint against the glyph set PAD_ACTIVE implies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_GLYPH = {
    "ArrowLeft": "◀", "ArrowRight": "▶", "ArrowUp": "▲", "ArrowDown": "▼",
    " ": "A", "r": "R",
}
_ALL_GLYPHS = set(_GLYPH.values())


def _hint_glyphs(html: str) -> set[str]:
    m = re.search(r'<p class="touchhint">(.*?)</p>', html, re.S)
    text = m.group(1) if m else ""
    return {g for g in _ALL_GLYPHS if g in text}


def _pad_glyphs(html: str) -> set[str]:
    m = re.search(r"PAD_ACTIVE=new Set\((\[[^\]]*\])\)", html)
    active = set(json.loads(m.group(1))) if m else set()
    return {_GLYPH[k] for k in active if k in _GLYPH}


@dataclass(frozen=True)
class GameTouchHintResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_game_touch_hint_matches_pad() -> GameTouchHintResult:
    from sidra_ai.creation.games import generate_game

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1 (per template): the glyphs named in the hint are exactly the glyphs the
    #    pad draws - no phantom button, none of the drawn ones hidden.
    cases = {
        "釣りゲームを作って": "fishing",
        "シューティングを作って": "shooter",
        "レースを作って": "racing",
        "パズルを作って": "puzzle",
    }
    html_by_template: dict[str, str] = {}
    for request, template in cases.items():
        html = generate_game(request).html
        html_by_template[template] = html
        hint, pad = _hint_glyphs(html), _pad_glyphs(html)
        add(hint == pad,
            f"{template}: hint {sorted(hint)} != pad {sorted(pad)}")

    # 2: the specifics the constant hint got wrong, stated outright so a
    #    regression names the symptom, not just a set mismatch.
    add(not ({"◀", "▶", "▲", "▼"} & _hint_glyphs(html_by_template["fishing"])),
        "fishing hint still shows arrow buttons it has none of")
    add("A" not in _hint_glyphs(html_by_template["racing"]),
        "racing hint still shows an A button it has none of")
    add({"▲", "▼"} <= _hint_glyphs(html_by_template["puzzle"]),
        "puzzle hint still hides its ▲▼ buttons")

    total = len(cases) + 3
    return GameTouchHintResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["GameTouchHintResult", "evaluate_game_touch_hint_matches_pad"]
