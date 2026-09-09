"""C-1604: the art title must strip every ART kind word, not just アート/art.

The intent detector routes 壁紙/wallpaper/生成アート/abstract art/digital art/…
to the art generator, but the title stripped only アート/art, so a subject kept
the kind word (「猫の壁紙」) or a compound cue was half-stripped to a broken
fragment (「海の生成アート」 -> 「海の生成」). The suffix now matches the cue set.
"""

from __future__ import annotations

from sidra_ai.creation.art import _title_from
from sidra_ai.evals.art_title_drops_all_kind_words import (
    evaluate_art_title_drops_all_kind_words,
)


def test_art_title_kind_eval_passes():
    result = evaluate_art_title_drops_all_kind_words()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_kind_words_are_stripped_to_the_subject():
    assert _title_from("猫の壁紙を作って") == "猫"
    assert _title_from("海の生成アートを作って") == "海"
    assert _title_from("森のabstract artを作って") == "森"
    assert _title_from("夕焼けのwallpaperを作って") == "夕焼け"


def test_subject_patterns_and_bare_kinds_are_unchanged():
    # 螺旋/幾何学模様 are the subject, not a kind word (non-regression, C-1265).
    assert _title_from("螺旋のアートを作って") == "螺旋"
    assert _title_from("幾何学模様のアートを作って") == "幾何学模様"
    # A bare kind word remains its own title rather than blanking.
    assert _title_from("アートを作って").strip()
    assert _title_from("壁紙を作って").strip()
