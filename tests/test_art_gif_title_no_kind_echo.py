"""C-1265: art and GIF titles drop the kind noun, like every other generator.

「螺旋のアートを作って」 titled 「螺旋のアート」 and the summary said 「…のジェネラ
ティブアート」 - アート twice; 「猫のGIFを作って」 → 「猫のGIF」 → 「…のアニメ GIF」.
The title is the subject alone now (「螺旋」, 「猫」), matching documents (C-1246),
decks (C-1249), 3D models and games.
"""

from __future__ import annotations

from sidra_ai.creation.art import _title_from as art_title
from sidra_ai.creation.gifs import _title_from as gif_title
from sidra_ai.evals.art_gif_title_no_kind_echo import (
    evaluate_art_gif_title_no_kind_echo,
)


def test_art_gif_title_no_kind_echo_eval_passes():
    result = evaluate_art_gif_title_no_kind_echo()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_art_title_drops_kind_word():
    assert art_title("螺旋のアートを作って") == "螺旋"
    assert art_title("フローアートを作って") == "フロー"
    assert art_title("幾何学模様のアートを作って") == "幾何学模様"
    # A bare kind word keeps a title rather than emptying out.
    assert art_title("アートを作って").strip()


def test_gif_title_drops_kind_word():
    assert gif_title("猫のGIFを作って") == "猫"
    assert gif_title("鳥のアニメGIFを作って") == "鳥"
    assert gif_title("花のGIFを作って") == "花"
    assert gif_title("GIFを作って").strip()


def test_non_kind_titles_unchanged():
    # A subject that does not end in a kind word is untouched.
    assert art_title("夕焼けを作って") == "夕焼け"
    assert gif_title("波を作って") == "波"
