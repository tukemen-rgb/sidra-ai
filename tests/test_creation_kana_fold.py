"""One program per meaning, not one program per script.

Measured before fixed: 「ぜるだみたいなげーむつくって」 fell through to the
fishing default while the katakana spelling routed to the adventure - the
vocabulary tables are katakana and kanji, and nothing folded the scripts
together. ``fold_kana`` is applied to both sides of every comparison and
never to stored text; these tests pin the fold itself, the routing it
repairs, and the questions it must not break.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SYSTEM_PROMPT
from sidra_ai.creation.games import choose_template, detect_genre
from sidra_ai.creation.intent import CreationKind, detect_creation_intent, fold_kana


def test_the_fold_maps_hiragana_onto_katakana_and_nothing_else() -> None:
    assert fold_kana("ぜるだ") == "ゼルダ"
    assert fold_kana("げーむ") == "ゲーム"
    assert fold_kana("ゼルダ") == "ゼルダ"
    assert fold_kana("game 作って 123") == "game 作ッテ 123"


@pytest.mark.parametrize(
    "text, kind, template",
    [
        ("ぜるだみたいなげーむつくって", CreationKind.GAME, "adventure"),
        ("どらごんぼーるのばとるつくって", CreationKind.GAME, "duel"),
        ("しゅーてぃんぐげーむ作って", CreationKind.GAME, "shooter"),
        ("ぱずるつくって", CreationKind.GAME, "puzzle"),
        ("きゃっちげーむつくって", CreationKind.GAME, "catch"),
        ("れぽーとつくって", CreationKind.DOCUMENT, None),
        ("じふつくって", CreationKind.GIF, None),
        ("あーとつくって", CreationKind.ART, None),
    ],
)
def test_hiragana_spellings_route_like_their_katakana_twins(
    text: str, kind: CreationKind, template: str | None
) -> None:
    intent = detect_creation_intent(text)
    assert intent.kind is kind and intent.routes
    if template is not None:
        assert choose_template(text) == template


def test_hiragana_questions_are_still_questions() -> None:
    """The fold must not push questions into the creation route."""

    assert not detect_creation_intent("ぱずるのつくりかたをおしえて").is_creation
    assert not detect_creation_intent("ぜるだとは").is_creation


def test_genre_honesty_sees_through_the_spelling() -> None:
    """Within the fold's honest reach: kana-to-kana. 「かくとう」→「格闘」 is
    kana-to-kanji and needs a morphological layer this fold does not claim;
    the katakana vocabulary words themselves must match from hiragana."""

    genre = detect_genre("ばとるげーむつくって")
    assert genre is not None and genre.template == "duel"
    still_missing = detect_genre("格ゲーつくって")
    assert still_missing is not None and still_missing.template == "fighter"


def test_the_prompt_pins_the_answer_language() -> None:
    """The 2026-08-27 incident: a Japanese question answered in confusing
    English, with nothing in the prompt forbidding it. Now there is."""

    assert "日本語の質問には必ず日本語" in SYSTEM_PROMPT
    assert "Answer in the language of the question" in SYSTEM_PROMPT
