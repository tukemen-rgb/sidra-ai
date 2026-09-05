"""C-1259: a game's subtitle names its genre in Japanese, not the key.

Every generated page's subtitle read 「難易度 normal / テンプレート fishing」 - the
internal template key, in English. Now it reads 「難易度 X / ジャンル <日本語>」,
the 「難易度 X」 half unchanged (other tests pin it) and the trademark-decline
prefix still prepended.
"""

from __future__ import annotations

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.evals.game_tagline_genre_localized import (
    evaluate_game_tagline_genre_localized,
)


def test_game_tagline_genre_localized_eval_passes():
    result = evaluate_game_tagline_genre_localized()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 2 * len(TEMPLATES)


def test_subtitle_names_genre_in_japanese_not_key():
    game = generate_game("レースゲームを作って")
    assert game.tagline == "難易度 normal / ジャンル レース"
    assert "テンプレート racing" not in game.html
    assert "ジャンル レース" in game.html


def test_difficulty_half_is_unchanged():
    # The 「難易度 {difficulty}」 half is what other tests rely on.
    for difficulty in ("easy", "normal", "hard"):
        game = generate_game("釣りゲームを作って", difficulty=difficulty)
        assert game.tagline.startswith(f"難易度 {difficulty} / ")
        assert "ジャンル 釣り" in game.tagline


def test_trademark_decline_prefix_still_prepends():
    # A trademarked name still gets the original-version notice, now before the
    # localized subtitle.
    game = generate_game("マリオみたいなゲームを作って")
    assert "オリジナル版" in game.tagline
    assert "ジャンル" in game.tagline
