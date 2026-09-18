"""The words the canvas draws, in both languages, in one table (C-1959).

C-1956 put the page's frame into the language of the request and C-1957 the
start screen's three lines. What a player looks at for the whole of a go -
the HUD row, the clock badge, the banner that ends it, the result strip -
was still Japanese whatever was asked, because those words are written
straight into the JavaScript each module hands to the page.

Measured before it was written: a whole go of ``catch``, run to its end on
a recording context, draws eight distinct shapes. Seven carry Japanese, and
five of those come from ``round.py`` - they are on every template. So the
table is small, and most of it is shared.

**One table, both languages.** Every row here is a word the canvas draws,
with the Japanese it has always drawn and the English beside it. Nothing
here is a second table that could drift from a first: the Japanese column
IS what the pages used to carry as literals, moved rather than copied.

**Injected once.** ``words_js`` writes the chosen column into the page as
``CW``, ahead of every preamble, and the drawing code names ``CW.score``
where it used to carry 「得点」. A template that wants a word the table does
not have cannot silently fall back to Japanese - ``CW.whatever`` is
``undefined`` and the judge sees it.

**Guarded at import.** A row missing either language, or an English value
that still carries Japanese script, raises here rather than shipping a half
translated page (C-1945, C-1951, C-1957).
"""

from __future__ import annotations

import json
import re

#: ``key: (Japanese, English)``. Order is the order a player meets them:
#: the HUD row, then the clock, then the end of a go, then the strip.
CANVAS_WORDS: dict[str, tuple[str, str]] = {
    # --- the HUD row, while playing ---
    "score": ("得点", "score"),
    "caught": ("受け", "caught"),
    "missed": ("こぼし", "missed"),
    "move_hint": ("← → またはマウスで動かす", "← → or the mouse to move"),
    # --- the clock badge (round.py), on every template ---
    "time_left": ("のこり", "left"),
    # --- the banner that ends a go ---
    "time_up": ("ここまで", "Time's up"),
    "time_up_said": ("ここまで。", "Time's up."),
    "again": ("R / タップでもう一度", "R / tap to play again"),
    "copy": ("C / 結果をコピー", "C / copy the result"),
    # --- the result strip under it ---
    "best_new": ("自己ベスト更新", "a personal best"),
    "best": ("自己ベスト", "best"),
    "best_open": ("（自己ベスト ", " (best "),
    "best_close": ("）", ")"),
    "to_go_open": ("（あと ", " ("),
    "to_go_close": ("）", " to go)"),
    "daily": ("今日の挑戦", "today's run"),
    "day_open": ("（", " ("),
    "day_close": (" 日目）", " days running)"),
    "recent": ("直近", "recent"),
    "unlock_open": ("新しい見た目「", "a new look, "),
    "unlock_close": ("」が開きました", ", is open"),
}

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

_EMPTY = sorted(k for k, v in CANVAS_WORDS.items() if not v[0] or not v[1])
_UNTRANSLATED = sorted(k for k, v in CANVAS_WORDS.items() if _JAPANESE.search(v[1]))

if _EMPTY or _UNTRANSLATED:  # pragma: no cover - import-time guard
    raise RuntimeError(
        f"canvaswords.CANVAS_WORDS has empty rows {_EMPTY} and still carries "
        f"Japanese in the English column of {_UNTRANSLATED}"
    )


def words_js(*, in_japanese: bool = True) -> str:
    """The chosen column, as the ``CW`` the page's drawing code reads."""

    column = {key: pair[0 if in_japanese else 1] for key, pair in CANVAS_WORDS.items()}
    return "const CW=" + json.dumps(column, ensure_ascii=False) + ";\n"


__all__ = ["CANVAS_WORDS", "words_js"]
