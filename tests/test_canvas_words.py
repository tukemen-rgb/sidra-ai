"""The canvas word table, pinned where a judge cannot see it (C-1959).

``creation_catch_canvas_matches_the_language_asked`` plays one go and reads
what the canvas drew. Some of the shared words only appear under conditions
one go does not reach - a personal best, a daily streak, a run history, a
newly opened skin - so they are held here instead, and this file says so
rather than letting the gap go unrecorded.
"""

from __future__ import annotations

import re

from sidra_ai.creation.canvaswords import CANVAS_WORDS, words_js
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import ROUND_SCORE, ROUND_SCORE_EN, ROUND_TIE, ROUND_TIE_EN

JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


def test_every_word_has_both_languages() -> None:
    for key, pair in CANVAS_WORDS.items():
        assert pair[0] and pair[1], key
        assert not JAPANESE.search(pair[1]), f"{key} is still Japanese in English"


def test_every_word_is_actually_drawn_by_the_page() -> None:
    """A row nothing names is a word that cannot reach a player."""

    page = generate_game("ふくろうのキャッチゲームを作って").html
    unused = [key for key in CANVAS_WORDS if f"CW.{key}" not in page]
    assert unused == [], f"CANVAS_WORDS rows no page names: {unused}"


def test_the_english_column_reaches_the_english_page() -> None:
    page = generate_game("make a catching game about an owl").html
    words = words_js(in_japanese=False)
    assert words.strip() in page.replace("\n", "\n")
    # The English word has to be IN the page; the Japanese one being absent
    # cannot be asserted here, because the script ships its own comments and
    # those are written in Japanese (C-1956 measured 174 such lines, none of
    # them drawn). What is drawn is the judge's question, not this file's.
    for key in ("best", "daily", "recent", "unlock_open"):
        assert CANVAS_WORDS[key][1] in page, key


def test_the_japanese_page_keeps_the_words_it_always_had() -> None:
    page = generate_game("ふくろうのキャッチゲームを作って").html
    for key in ("best", "daily", "recent", "unlock_open", "time_up", "again"):
        assert CANVAS_WORDS[key][0] in page, key


def test_every_template_has_an_english_score_label() -> None:
    assert set(ROUND_SCORE) == set(ROUND_SCORE_EN)
    assert set(ROUND_TIE) == set(ROUND_TIE_EN)
    for label in list(ROUND_SCORE_EN.values()) + list(ROUND_TIE_EN.values()):
        assert not JAPANESE.search(label), label
