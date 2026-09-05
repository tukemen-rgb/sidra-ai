"""C-1249: a deck's cover names the subject, not subject + 「スライド」.

「GAMEYARD の強みのスライドを作って」 titled the deck 「GAMEYARD の強みのスライド」,
so the cover slide and <title> said 「スライド」 back. The trailing slide-kind
word is dropped from the title now, while a request without one is left alone
and a bare 「スライドを作って」 falls back to the outline's default title.
"""

from __future__ import annotations

from sidra_ai.creation.decks import _title_from, generate_deck
from sidra_ai.evals.deck_title_no_kind_echo import evaluate_deck_title_no_kind_echo


def test_deck_title_no_kind_echo_eval_passes():
    result = evaluate_deck_title_no_kind_echo()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_kind_word_dropped_from_deck_title():
    assert _title_from("GAMEYARD の強みのスライドを作って", "既定") == "GAMEYARD の強み"
    assert _title_from("営業用のデッキを作って", "既定") == "営業用"
    assert _title_from("進捗のプレゼンを作って", "既定") == "進捗"
    assert _title_from("紹介スライドショーを作って", "既定") == "紹介"  # longest match
    assert _title_from("決算プレゼンテーションを作成して", "既定") == "決算"


def test_non_kind_deck_title_unchanged():
    assert _title_from("新機能を作って", "既定") == "新機能"
    # a kind word mid-phrase is not the tail, so it stays
    assert _title_from("スライド設計の指針を作って", "既定") == "スライド設計の指針"


def test_bare_kind_word_falls_back_to_default():
    assert _title_from("スライドを作って", "SIDRA AI のご提案") == "SIDRA AI のご提案"
    assert _title_from("デッキを作って", "進捗報告") == "進捗報告"


def test_rendered_cover_says_subject_once():
    html = generate_deck("GAMEYARD の強みのスライドを作って").html
    assert "<h1>GAMEYARD の強み</h1>" in html
    assert "の強みのスライド</h1>" not in html
    assert "<title>GAMEYARD の強み</title>" in html
