"""C-1465: a deck's cover title drops the format words the request phrased.

「会議のスライドをパワポで作って」 stacks two kind words with a particle between;
stripping the kind and the particle once each left 「会議のスライドをパワポ」 on the
cover. The title now peels them repeatedly, and the full 「パワーポイント」 spelling
was added to the kind list.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.decks import generate_deck
from sidra_ai.evals.deck_title_drops_format_words import (
    evaluate_deck_title_drops_format_words,
)


def test_deck_title_format_eval_passes():
    result = evaluate_deck_title_drops_format_words()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("会議のスライドをパワポで作って", "会議"),
        ("企画のプレゼンをパワポで作成して", "企画"),
        ("提案資料をpptxで作成して", "提案"),
        ("営業戦略のスライドをパワーポイントで作って", "営業戦略"),
        ("プレゼンの極意をスライドで作って", "プレゼンの極意"),
    ],
)
def test_stacked_kind_words_are_peeled(request_text, expected):
    assert generate_deck(request_text).title == expected


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("会議のスライドを作って", "会議"),
        ("営業戦略のスライドを作って", "営業戦略"),
        ("資料設計の指針のスライドを作って", "資料設計の指針"),
    ],
)
def test_single_kind_word_is_not_over_stripped(request_text, expected):
    assert generate_deck(request_text).title == expected


@pytest.mark.parametrize(
    "request_text",
    ["スライドを作って", "パワポで作って"],
)
def test_only_kind_words_fall_to_default(request_text):
    # The pitch outline's default cover, not a bare kind word.
    assert generate_deck(request_text).title == "SIDRA AI のご提案"
