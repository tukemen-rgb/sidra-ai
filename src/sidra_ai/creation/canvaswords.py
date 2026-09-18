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
    # --- fishing (C-1960) ---
    "fishing_hint": ("SPACE / クリックで合わせる", "SPACE / click to time it"),
    "catches": ("釣果", "catches"),
    "crit": ("会心", "perfect"),
    "bullseye": ("ど真ん中。会心。", "Dead centre. Perfect."),
    "hooked": ("かかった。", "Hooked."),
    "got_away": ("逃げられた。", "It got away."),
    # --- puzzle (C-1960) ---
    "hammers": ("つち", "hammers"),
    "clump_open": ("このかたまり ", "this clump: "),
    "cant_clear": ("ここは消せない", "this one cannot be cleared"),
    "all_cleared": ("全部消えた。", "All cleared."),
    "no_moves": ("もう消せる手がない。", "No moves left."),
    "again_space_r": (" / SPACE か R でもう一度", " / SPACE or R to play again"),
    # --- platformer (C-1960) ---
    "gems": ("宝石", "gems"),
    "falls": ("落下", "falls"),
    "lamp_on": ("  灯籠 点", "  lantern lit"),
    "reach_the_flag": ("足場を渡って、旗まで。", "Cross the platforms to the flag."),
    "lamp_lit": ("灯籠がともった。落ちてもここから。",
                 "The lantern is lit. A fall puts you back here now."),
    "lamp_cost_open": ("灯籠は宝石 ", "the lantern lights for "),
    "lamp_cost_mid": (" 個で点く（いま ", " gems (you have "),
    "lamp_cost_close": (" 個）。", ")."),
    "back_to_lamp": ("灯籠まで戻された。", "Back to the lantern."),
    "back_to_start": ("足場のはじめに戻された。", "Back to the first platform."),
    "light_reached": ("灯りは旗までとどいた。", "The light reached the flag."),
    "again_r_tap": (" / R かタップでもう一度", " / R or tap to play again"),
    # --- marble (C-1960) ---
    "score_kana": ("スコア", "score"),
    "gates": ("ゲート", "gates"),
    "distance": ("距離", "distance"),
    "hit_block": ("ブロックに当たった。", "You hit a block."),
    "course_done": ("コースを走り切った。", "You finished the course."),
    # --- kaiju (C-1960) ---
    "cycles": ("周期", "cycles"),
    "legs": ("脚", "legs"),
    "kaiju_silent": ("巨獣、沈黙。", "The kaiju falls silent."),
    "squad_back": ("部隊は退いた。", "The squad pulled back."),
    "again_key": ("R でもう一度", "R to play again"),
    # --- the counters English does not say (C-1960) ---
    #
    # 「個」 and 「回」 count things a number already counts in English, so
    # their English column is deliberately empty. An empty value is a
    # mistake everywhere else, so every row that means to be empty is
    # named in EMPTY_IN_ENGLISH below and the guard checks the two agree.
    "n_things": (" 個", ""),
    "n_times": (" 回", ""),
}

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: The rows whose English is meant to be empty: Japanese counters that a
#: number says by itself in English. Declared rather than allowed, so a row
#: that simply never got its English still raises.
EMPTY_IN_ENGLISH = frozenset({"n_things", "n_times"})

_EMPTY = sorted(
    k for k, v in CANVAS_WORDS.items()
    if not v[0] or (not v[1] and k not in EMPTY_IN_ENGLISH)
)
_UNTRANSLATED = sorted(k for k, v in CANVAS_WORDS.items() if _JAPANESE.search(v[1]))
_DECLARED_BUT_FILLED = sorted(
    k for k in EMPTY_IN_ENGLISH if k not in CANVAS_WORDS or CANVAS_WORDS[k][1]
)

if _EMPTY or _UNTRANSLATED or _DECLARED_BUT_FILLED:  # pragma: no cover
    raise RuntimeError(
        f"canvaswords.CANVAS_WORDS has empty rows {_EMPTY}, still carries "
        f"Japanese in the English column of {_UNTRANSLATED}, and declares "
        f"{_DECLARED_BUT_FILLED} empty while they are not"
    )


def words_js(*, in_japanese: bool = True) -> str:
    """The chosen column, as the ``CW`` the page's drawing code reads."""

    column = {key: pair[0 if in_japanese else 1] for key, pair in CANVAS_WORDS.items()}
    return "const CW=" + json.dumps(column, ensure_ascii=False) + ";\n"


_SAY_LITERAL = re.compile(r"say\('([^']+)'\)")
_SAY_WORD = re.compile(r"say\(CW\.(\w+)\)")


def said_lines(script: str, *, in_japanese: bool = True) -> list[str]:
    """Every whole line the page's ``say()`` can put on screen.

    Before C-1960 a reader could find these by looking for ``say('...')``
    in the page, and two test files did exactly that. Now a template says
    ``say(CW.lamp_lit)`` instead, so the same question has to be asked of
    the table as well - otherwise a template that still speaks looks mute,
    which is how a reading-speed test can pass by measuring nothing.

    Composed calls (a ternary, or a sentence built around a number) are
    left out here exactly as they were left out before: this returns the
    lines that are one whole string, which is what the callers measure.
    """

    column = 0 if in_japanese else 1
    lines = list(_SAY_LITERAL.findall(script))
    lines += [
        CANVAS_WORDS[key][column]
        for key in _SAY_WORD.findall(script)
        if key in CANVAS_WORDS
    ]
    return lines


__all__ = ["CANVAS_WORDS", "EMPTY_IN_ENGLISH", "said_lines", "words_js"]
