"""C-1841: an English request is titled by its subject, not by its sentence.

Japanese puts the making verb last, so every generator's split removes it;
English puts it first, and only games had a rule for that. Twelve of fifteen
English titles were the request itself.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation import models3d
from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.vocabulary import drop_english_frame, drop_size_phrases
from sidra_ai.evals.title_in_english import (
    ENGLISH,
    JAPANESE,
    _title,
    evaluate_title_in_english,
)


def test_title_english_eval_passes():
    result = evaluate_title_in_english()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


@pytest.mark.parametrize(("kind", "request_text", "expected"), ENGLISH)
def test_an_english_request_is_titled_by_its_subject(kind, request_text, expected):
    assert _title(kind, request_text) == expected


@pytest.mark.parametrize(("kind", "request_text", "expected"), JAPANESE)
def test_every_japanese_title_is_unchanged(kind, request_text, expected):
    assert _title(kind, request_text) == expected


def test_the_game_generator_is_untouched():
    assert generate_game("make a game about a cat").title == "cat"
    assert generate_game("please make a puzzle game").title == "puzzle"


def test_a_size_behind_the_kind_word_comes_off_in_japanese_too():
    assert generate_document("収益化のレポートを3ページで作って").title == "収益化"


def test_an_english_size_is_a_size_and_a_numbered_noun_is_not():
    assert drop_size_phrases("3 page") == ""
    assert drop_size_phrases("page 3 of the report") == "page 3 of the report"


def test_a_number_inside_a_subject_is_not_a_size():
    """The other loop's cases (C-1822), which caught this cycle cutting them."""

    assert drop_size_phrases("5枚組の写真集") == "5枚組の写真集"
    assert drop_size_phrases("300万円の予算") == "300万円の予算"
    assert drop_size_phrases("第3四半期") == "第3四半期"
    assert drop_size_phrases("5枚のスライド") == "スライド"


def test_the_frame_rule_has_one_home():
    # C-1839 gave models3d its own copy; this folded it into vocabulary.
    assert not hasattr(models3d, "_EN_HEAD")
    assert drop_english_frame("make a gif of a fish") == "fish"
