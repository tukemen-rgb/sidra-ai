"""C-1287: the game's touch hint names exactly the buttons the pad draws.

The pad draws only the keys the game reads (PAD_ACTIVE, C-1244), but the hint was
the constant 「◀ ▶ / A」 on every template - naming buttons fishing has none of,
an A racing has none of, and hiding a puzzle's ▲▼. The hint is now built from the
same PAD_ACTIVE.
"""

from __future__ import annotations

import json
import re

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.game_touch_hint_matches_pad import (
    evaluate_game_touch_hint_matches_pad,
)

_GLYPH = {
    "ArrowLeft": "◀", "ArrowRight": "▶", "ArrowUp": "▲", "ArrowDown": "▼",
    " ": "A", "r": "R",
}


def _hint(html: str) -> str:
    return re.search(r'<p class="touchhint">(.*?)</p>', html, re.S).group(1)


def _pad_glyphs(html: str) -> set[str]:
    active = set(json.loads(re.search(r"PAD_ACTIVE=new Set\((\[[^\]]*\])\)", html).group(1)))
    return {_GLYPH[k] for k in active if k in _GLYPH}


def test_game_touch_hint_matches_pad_eval_passes():
    result = evaluate_game_touch_hint_matches_pad()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_hint_glyphs_equal_pad_glyphs_across_templates():
    all_glyphs = set(_GLYPH.values())
    for request in ("釣りゲームを作って", "シューティングを作って",
                    "レースを作って", "パズルを作って"):
        html = generate_game(request).html
        hint = {g for g in all_glyphs if g in _hint(html)}
        assert hint == _pad_glyphs(html), request


def test_fishing_hint_has_no_arrows_puzzle_has_up_down():
    fishing = _hint(generate_game("釣りゲームを作って").html)
    assert not ({"◀", "▶", "▲", "▼"} & set(fishing))
    puzzle = _hint(generate_game("パズルを作って").html)
    assert "▲" in puzzle and "▼" in puzzle
