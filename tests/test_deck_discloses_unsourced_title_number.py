"""C-1799: a deck discloses an unsourced figure in its title, like the report (C-1772).

「解約率30%の改善」 puts 30% on the cover; with nothing sourcing it the deck now
scopes its numbers promise to the body and caveats the title, while a clean title
or a number the evidence supports keeps the original blanket assurance.
"""

from __future__ import annotations

from sidra_ai.creation.decks import Fact, generate_deck
from sidra_ai.evals.deck_discloses_unsourced_title_number import (
    evaluate_deck_discloses_unsourced_title_number,
)

_CAVEAT = "タイトルの数値は索引した根拠では確認できていません"


def test_deck_title_number_eval_passes():
    result = evaluate_deck_discloses_unsourced_title_number()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_unsourced_title_number_is_disclosed():
    html = generate_deck("解約率30%の改善のスライドを作って").html
    assert _CAVEAT in html
    assert "本文の数字は" in html
    assert "推測で埋めません" in html  # the footer still stands


def test_a_clean_title_keeps_the_blanket_assurance():
    html = generate_deck("新商品の企画のスライドを作って").html
    assert _CAVEAT not in html
    assert "。数字は索引した文書から引いたものだけ" in html


def test_a_sourced_title_number_is_not_caveated():
    html = generate_deck(
        "解約率30%の改善のスライドを作って",
        facts=[Fact(text="解約率は30%改善した", source="repo@abc:docs/kpi.md")],
    ).html
    assert _CAVEAT not in html
