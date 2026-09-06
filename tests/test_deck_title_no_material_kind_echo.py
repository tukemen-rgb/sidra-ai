"""C-1282: a deck cover does not echo 「資料」, the everyday word for a deck.

The intent detector routes every 「X資料」 to DECK, but the deck title stripper
(C-1249) had only スライド/プレゼン/デッキ and missed the 「資料」 forms, so
「…のプレゼン資料を作って」 titled the cover 「…のプレゼン資料」. The document
title already strips 「資料」; this closes the same gap for the deck.
"""

from __future__ import annotations

from sidra_ai.creation.decks import generate_deck
from sidra_ai.evals.deck_title_no_material_kind_echo import (
    evaluate_deck_title_no_material_kind_echo,
)


def test_deck_title_no_material_kind_echo_eval_passes():
    result = evaluate_deck_title_no_material_kind_echo()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_presentation_material_compound_strips_whole():
    deck = generate_deck("新機能ローンチの週次進捗のプレゼン資料を作って")
    assert deck.title == "新機能ローンチの週次進捗"
    assert "<h1>新機能ローンチの週次進捗</h1>" in deck.html
    assert "資料</h1>" not in deck.html


def test_subject_plus_material_keeps_subject():
    assert generate_deck("企画資料を作って").title == "企画"
    assert generate_deck("週次進捗資料を作って").title == "週次進捗"


def test_bare_material_words_fall_back():
    for phrase in ("プレゼン資料", "プレゼンテーション資料", "スライド資料", "資料"):
        title = generate_deck(f"{phrase}を作って").title
        assert title.strip() and "資料" not in title, phrase


def test_material_inside_subject_is_kept():
    assert generate_deck("資料設計の指針を作って").title == "資料設計の指針"


def test_c1249_slide_family_still_stripped():
    assert generate_deck("GAMEYARD の強みのスライドを作って").title == "GAMEYARD の強み"
