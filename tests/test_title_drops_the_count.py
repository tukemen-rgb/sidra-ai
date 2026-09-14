"""C-1833: the artifact is named after its subject, not after how many.

「5枚のスライドを作って」 was titled 「5枚」, 「30フレームのGIF」 was 「30フレーム」,
「魚の3Dモデルを3つ」 was 「魚3つ」 - and 「新商品のスライドを5枚で作って」 kept the
kind word too, since the strip that removes it is anchored to the end.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.gifs import generate_gif
from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.creation.vocabulary import drop_size_phrases
from sidra_ai.evals.title_drops_the_count import evaluate_title_drops_the_count

_DIGITS = re.compile(r"\d")


def test_title_count_eval_passes():
    result = evaluate_title_drops_the_count()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


@pytest.mark.parametrize(
    "request_text",
    ["5枚のスライドを作って", "10枚の新商品のスライドを作って", "新商品のスライドを5枚で作って"],
)
def test_a_deck_is_not_named_after_its_size(request_text):
    assert not _DIGITS.search(generate_deck(request_text).title)


@pytest.mark.parametrize("request_text", ["30フレームのGIFを作って", "5秒の魚のGIFを作って"])
def test_a_gif_is_not_named_after_its_length(request_text):
    assert not _DIGITS.search(generate_gif(request_text).title)


@pytest.mark.parametrize(
    "request_text", ["魚の3Dモデルを3つ作って", "3つの船の3Dモデルを作って"]
)
def test_a_model_is_not_named_after_its_count(request_text):
    assert not _DIGITS.search(generate_model3d(request_text).title)


def test_the_kind_word_comes_off_once_the_count_is_gone():
    assert generate_deck("新商品のスライドを5枚で作って").title == "新商品"


def test_the_3d_generator_got_the_adverb_rule_it_was_missed_by():
    # C-1829 widened six generators and left this one out.
    assert generate_model3d("魚の3Dモデルを今すぐ作って").title == "魚"
    assert generate_model3d("魚の3Dモデルをまとめて作って").title == "魚"


def test_a_request_with_no_count_is_untouched():
    assert generate_deck("新商品のスライドを作って").title == "新商品"
    assert generate_gif("魚のGIFを作って").title == "魚"
    assert generate_model3d("魚の3Dモデルを作って").title == "魚"


def test_the_rule_only_cuts_a_number_with_a_unit():
    assert drop_size_phrases("2026年のゲーム") == "2026年のゲーム"
    assert drop_size_phrases("点滅する魚") == "点滅する魚"
    assert drop_size_phrases("いつつの星") == "いつつの星"


def test_the_documents_own_rule_still_stands():
    assert generate_document("2000字の収益化のレポートを作って").title == "収益化"
