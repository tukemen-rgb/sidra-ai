"""Stripping the English frame never cuts into a word (C-1913)."""

from __future__ import annotations

import pytest

from sidra_ai.creation.vocabulary import drop_english_frame
from sidra_ai.evals.english_frame_keeps_whole_words import (
    CASES,
    evaluate_english_frame_keeps_whole_words,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_english_frame_keeps_whole_words()


def test_no_word_is_cut(result):
    assert result.passed, "; ".join(result.failures)


def test_every_case_was_read(result):
    assert len(result.readings) == len(CASES)
    assert result.checks_total == result.checks_passed


@pytest.mark.parametrize(
    "request_text,subject",
    [
        # The article is a whole word, not a prefix.
        ("draw an abstract picture", "abstract picture"),
        ("create an artwork", "artwork"),
        # ...and a subject that merely starts with a/an keeps its letter.
        ("make abstract art", "abstract art"),
        ("generate anime wallpaper", "anime wallpaper"),
    ],
)
def test_the_shapes_that_lost_a_letter(request_text, subject):
    assert drop_english_frame(request_text) == subject


def test_japanese_requests_are_untouched():
    # The stripper runs unconditionally; it must not find an English frame
    # in a Japanese sentence.
    for text in ("海のアートを作って", "抽象的な絵を作って"):
        assert drop_english_frame(text) == text
