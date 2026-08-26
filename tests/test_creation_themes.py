"""A named palette reaches the page; an unnamed one changes nothing.

Both halves are load-bearing, and the second is the one a "themes" feature
loses quietly. A generator that switched its default while gaining three
themes would pass every test about switching and would have changed what
every operator gets without anyone asking for it.

The contrast checks are here for the same reason the anti-fabrication checks
are in the deck tests: a palette that cannot be read is not a style choice.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.games import GAMEYARD_TOKENS, TEMPLATES, generate_game, validate_game_html
from sidra_ai.creation.themes import (
    CONTRAST_FLOORS,
    DEFAULT_THEME,
    THEMES,
    TOKEN_KEYS,
    contrast_ratio,
    readable_themes,
    select_theme,
    validate_theme,
)


def test_the_catalogue_offers_at_least_three_themes() -> None:
    assert len(readable_themes()) >= 3


@pytest.mark.parametrize("key", sorted(THEMES))
def test_every_theme_defines_every_token(key: str) -> None:
    """A missing token renders as a literal ``None`` in the stylesheet."""

    assert set(THEMES[key].tokens) == set(TOKEN_KEYS)


@pytest.mark.parametrize("key", sorted(THEMES))
def test_every_theme_is_readable(key: str) -> None:
    verdict = validate_theme(THEMES[key])
    assert verdict["readable"], verdict["failures"]


def test_the_contrast_floors_are_not_rigged_to_pass() -> None:
    """A floor low enough for anything measures nothing.

    Grey-on-grey has to fail, or the check above is decoration.
    """

    assert contrast_ratio("#777777", "#6f6f6f") < 1.5
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert all(floor >= 3.0 for _, _, floor in CONTRAST_FLOORS)


def test_the_default_theme_is_the_sites_own_palette() -> None:
    """Derived, not retyped: two copies would let the default drift."""

    tokens = DEFAULT_THEME.tokens
    assert tokens["bg"] == GAMEYARD_TOKENS["bg"]
    assert tokens["surface"] == GAMEYARD_TOKENS["surface"]
    assert tokens["accent"] == GAMEYARD_TOKENS["cyan"]
    assert tokens["alert"] == GAMEYARD_TOKENS["magenta"]


def test_a_request_naming_no_theme_gets_the_default() -> None:
    for message in ("釣りゲームを作って", "デッキを作って", "資料を作って"):
        assert select_theme(message) is DEFAULT_THEME


def test_a_colour_word_alone_is_not_a_theme_request() -> None:
    """「紙の資料」 names the subject, not the palette.

    Same shape as the verb-plus-artifact rule in creation.intent: one signal
    on its own reads ordinary subject matter as an instruction.
    """

    assert select_theme("紙の資料を作って") is DEFAULT_THEME
    assert select_theme("緑の釣りゲームを作って") is DEFAULT_THEME
    assert select_theme("紙のテーマで資料を作って").key == "paper"


def test_the_cue_and_the_word_together_select_the_theme() -> None:
    assert select_theme("ターミナル配色でデッキを作って").key == "terminal"
    assert select_theme("夕暮れのテーマで").key == "dusk"


def test_the_latest_word_wins_a_tie() -> None:
    """Japanese puts the head last, so the nearer word to テーマ decides."""

    assert select_theme("紙ではなくターミナルのテーマで").key == "terminal"


@pytest.mark.parametrize("key", sorted(THEMES))
def test_a_named_theme_reaches_both_artifacts(key: str) -> None:
    theme = THEMES[key]
    request = f"{theme.words[0]}のテーマで"

    assert theme.tokens["bg"] in generate_game(f"{request}ゲームを作って").html
    assert theme.tokens["bg"] in generate_deck(f"{request}デッキを作って").html


@pytest.mark.parametrize("key", sorted(set(THEMES) - {DEFAULT_THEME.key}))
def test_a_named_theme_actually_changes_the_page(key: str) -> None:
    """Reaching the page is not enough if the page looks the same."""

    request = f"{THEMES[key].words[0]}のテーマで"

    assert generate_game(f"{request}ゲームを作って").html != generate_game("ゲームを作って").html
    assert generate_deck(f"{request}デッキを作って").html != generate_deck("デッキを作って").html


@pytest.mark.parametrize("key", sorted(THEMES))
def test_a_themed_game_is_still_playable(key: str) -> None:
    """A palette must not be able to break the artifact it colours."""

    request = f"{THEMES[key].words[0]}のテーマで"
    for template in TEMPLATES:
        verdict = validate_game_html(generate_game(f"{request}ゲームを作って", template=template).html)
        assert verdict["playable"], (key, template, verdict["failures"])


def test_a_theme_never_pulls_in_an_external_asset() -> None:
    """Themes are colours. A font or an image would need the network."""

    for key, theme in THEMES.items():
        html = generate_deck(f"{theme.words[0]}のテーマでデッキを作って").html
        assert "http://" not in html and "https://" not in html, key
        assert "@import" not in html, key
