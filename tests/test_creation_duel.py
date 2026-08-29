"""The duel template: the clash is the game, the franchise is not takeable.

The second directive video showed one moment - two fighters, charged
blasts, beams meeting in the middle. These tests pin that the request
routes there, the page plays by the house rules, the clash mechanics are
actually in the script, and the franchise name never survives onto the
artifact.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import (
    TEMPLATES,
    choose_template,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.intent import CreationKind, detect_creation_intent


def test_the_directive_request_routes_and_plays() -> None:
    intent = detect_creation_intent("ドラゴンボールのゲーム作って")
    assert intent.kind is CreationKind.GAME and intent.routes

    game = generate_game("ドラゴンボールのゲーム作って")
    assert game.template == "duel"
    verdict = validate_game_html(game.html)
    assert verdict["playable"], verdict["failures"]


@pytest.mark.parametrize(
    "request_text",
    ["ビームの撃ち合いゲームを作って", "エネルギー波で対戦するゲームを作って", "バトルゲームを作って"],
)
def test_genre_words_reach_the_duel_template(request_text: str) -> None:
    assert choose_template(request_text) == "duel"


def test_neighbouring_templates_are_not_stolen() -> None:
    assert choose_template("冒険ゲームを作って") == "adventure"
    assert choose_template("釣りゲームを作って") == "fishing"
    # 冒険 appears earlier in the chooser, so a request naming both stays an
    # adventure - the more specific world beats the more specific moment.
    assert choose_template("ドラゴンボールの冒険ゲームを作って") == "adventure"


def test_the_franchise_never_reaches_the_artifact() -> None:
    game = generate_game("ドラゴンボールのゲームを作って")

    assert "ドラゴンボール" not in game.title
    assert game.title == TEMPLATES["duel"].default_title
    assert "オリジナル版" in game.tagline
    assert "ドラゴンボール" not in game.html


def test_the_clash_mechanics_are_in_the_script() -> None:
    """Charge, lanes, and the push-of-war - the genre's spine."""

    html = generate_game("ビームの撃ち合いゲームを作って").html
    for marker in ("charge", "beamLane", "spark", "押し合い", "mash"):
        assert marker in html, marker


def test_the_opponent_is_seeded_by_the_request() -> None:
    same_a = generate_game("ビームの撃ち合いゲームを作って")
    same_b = generate_game("ビームの撃ち合いゲームを作って")
    other = generate_game("嵐のビームの撃ち合いゲームを作って")

    assert same_a.html == same_b.html
    assert same_a.html != other.html
    assert "SEED_TOKEN" not in same_a.html


def test_difficulty_changes_the_opponent() -> None:
    hard = generate_game("難しいビームの撃ち合いゲームを作って")
    assert "CSPEED=1.4" in hard.html


def test_the_page_keeps_every_house_rule() -> None:
    game = generate_game("ビームの撃ち合いゲームを作って")

    assert "http://" not in game.html and "https://" not in game.html
    assert "prefers-reduced-motion" in game.html
