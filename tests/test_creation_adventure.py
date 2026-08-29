"""The adventure template: the genre is buildable, the name is not takeable.

The directive was a video - an original top-down action-adventure made by
people who loved Minish Cap - plus 「ゼルダの伝説 不思議なぼうし作って」. So
the tests pin the two halves of that deal separately: the request routes and
produces a playable tile world (rooms, sword, key, chest, NPC), and the
trademark never survives onto the artifact, with the rename said out loud
rather than done silently.
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
    """「ゼルダの伝説 不思議なぼうしつくって」 - no word ゲーム anywhere."""

    intent = detect_creation_intent("ゼルダの伝説 不思議なぼうしつくって")
    assert intent.kind is CreationKind.GAME and intent.routes

    game = generate_game("ゼルダの伝説 不思議なぼうしつくって")
    assert game.template == "adventure"
    verdict = validate_game_html(game.html)
    assert verdict["playable"], verdict["failures"]


@pytest.mark.parametrize(
    "request_text",
    ["冒険ゲームを作って", "ダンジョン探索ゲームを作って", "adventure game を作って"],
)
def test_genre_words_reach_the_adventure_template(request_text: str) -> None:
    assert choose_template(request_text) == "adventure"


def test_existing_templates_are_not_stolen() -> None:
    assert choose_template("釣りゲームを作って") == "fishing"
    assert choose_template("キャッチゲームを作って") == "catch"


def test_the_trademark_never_reaches_the_artifact() -> None:
    """The genre is ours to build; the name is someone's. Openly swapped."""

    game = generate_game("ゼルダの伝説 不思議なぼうしを作って")

    assert "ゼルダ" not in game.title
    assert game.title == TEMPLATES["adventure"].default_title
    assert "オリジナル版" in game.tagline
    # The page's visible copy carries neither the mark nor a claim to it.
    assert "ゼルダ" not in game.html


def test_an_original_title_is_kept_untouched() -> None:
    """The guard fires on trademarks, not on the operator's own words."""

    game = generate_game("ほら穴の冒険を作って")
    assert game.title == "ほら穴の冒険"
    assert "オリジナル版" not in game.tagline


def test_the_world_is_seeded_by_the_request() -> None:
    same_a = generate_game("森の冒険を作って")
    same_b = generate_game("森の冒険を作って")
    other = generate_game("湖の冒険を作って")

    assert same_a.html == same_b.html
    assert same_a.html != other.html
    # The seed actually reaches the script, not only the title.
    assert "SEED_TOKEN" not in same_a.html


def test_difficulty_changes_the_numbers_not_the_wording() -> None:
    normal = generate_game("冒険ゲームを作って")
    hard = generate_game("難しい冒険ゲームを作って")

    assert normal.html != hard.html
    assert "ESPEED=1.2" in hard.html
    assert "ESPEED=0.8" in normal.html


def test_the_page_keeps_every_house_rule() -> None:
    game = generate_game("冒険ゲームを作って")

    assert "http://" not in game.html and "https://" not in game.html
    # The animation preamble is present, so torches freeze under reduced
    # motion instead of flickering at someone who asked them not to.
    assert "prefers-reduced-motion" in game.html


def test_the_world_has_the_promised_shape() -> None:
    """Three rooms, a sword, a key, a chest, an NPC line - the genre's spine."""

    html = generate_game("冒険ゲームを作って").html
    for marker in ("森のはずれ", "ひかり苔の洞窟", "風の祭壇", "鍵を手に入れた", "swing", "宝箱"):
        assert marker in html, marker


def test_a_zelda_question_is_still_a_question() -> None:
    assert not detect_creation_intent("ゼルダの伝説とは").is_creation
    assert not detect_creation_intent("ゼルダの伝説の作り方を教えて").is_creation


def test_the_map_reads_by_form_not_colour_alone() -> None:
    """Knowledge base §4: walls get edge highlights, doors get a chevron,
    and the pond is carved for real - the water tile shipped as dead code
    once, and 'defined' is not 'placed'."""

    html = generate_game("冒険ゲームを作って").html

    assert "pond(forest)" in html
    assert "closePath" in html  # the door chevron path
    assert "#ffffff2e" in html  # wall top highlight (form, not hue)
    assert "BORDER_TOKEN" not in html  # the wall colour token was substituted
