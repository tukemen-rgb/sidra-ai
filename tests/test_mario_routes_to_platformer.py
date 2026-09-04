"""C-1225: a マリオ request must build a platformer, with the name guarded.

「マリオみたいなゲーム」 detected no genre and fell to fishing, even though
マリオ was already a guarded trademark. It now routes to the platformer the
way ゼルダ routes to adventure; the title guard swaps the trademark for an
original name, and マリオカート still routes to racing (named first).
"""

from __future__ import annotations

from sidra_ai.creation.games import choose_template, detect_genre, generate_game
from sidra_ai.evals.mario_routes_to_platformer import evaluate_mario_routes_to_platformer


def test_mario_routes_eval_passes():
    result = evaluate_mario_routes_to_platformer()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_mario_requests_reach_platformer():
    for request in ("マリオみたいなゲームを作って", "マリオ風のゲーム", "マリオっぽいゲーム"):
        assert choose_template(request) == "platformer", request
        g = detect_genre(request)
        assert g is not None and g.template == "platformer", request


def test_mario_kart_still_races():
    assert choose_template("マリオカートみたいなレースゲーム") == "racing"


def test_generated_mario_game_hides_the_trademark():
    game = generate_game("マリオみたいなゲームを作って")
    assert game.template == "platformer"
    assert "マリオ" not in game.html
    assert "オリジナル版" in game.tagline
