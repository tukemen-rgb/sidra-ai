"""C-1609: a deck's number slide must not fill with identifier digits.

The pitch's 「根拠となる数字」 slide was chosen by "any digit anywhere", so a
capability sentence whose only digits were the 25 in 「BM25」 was filed as a
supporting figure. mentions_number now masks an identifier's digits (a digit
following an ASCII letter, across at most one hyphen) before looking for a
quantity, so BM25/FTS5/C-1234/GPT-6 are names again while 14/38, 512 MiB and
「GPT4は月20万円」 stay figures.
"""

from __future__ import annotations

from sidra_ai.creation.decks import BLANK, generate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_number_slide_rejects_identifier_digits import (
    evaluate_deck_number_slide_rejects_identifier_digits,
)


def _slide_text(deck, title: str) -> str:
    return " ".join(
        b for slide in deck.slides if slide.title == title for b in slide.bullets
    )


def test_deck_number_slide_eval_passes():
    result = evaluate_deck_number_slide_rejects_identifier_digits()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_identifier_digit_is_not_a_number():
    for text in ("BM25 で検索する。", "FTS5 に昇格した。", "C-1234 を起票した。",
                 "GPT-6 を評価した。", "S3 に保存する。", "v0.1 をリリースした。"):
        assert not Fact(text, "x").mentions_number(), text


def test_real_figure_still_counts():
    for text in ("14/38 だった。", "3 件残っている。", "512 MiB を予約する。",
                 "60Hz で測った。", "80.0% を達成した。", "GPT4は月20万円かかる。"):
        assert Fact(text, "x").mentions_number(), text


def test_identifier_fact_stays_off_the_number_slide():
    ident = Fact("SIDRA は BM25 の純 Python 検索で外部依存しない。", "docs/a.md")
    deck = generate_deck("提案スライドを作って", facts=[ident], outline="pitch")
    assert BLANK in _slide_text(deck, "根拠となる数字")


def test_real_figure_reaches_the_number_slide():
    metric = Fact("回答可能率は 14/38 だった。", "docs/b.md")
    deck = generate_deck("提案スライドを作って", facts=[metric], outline="pitch")
    assert "14/38" in _slide_text(deck, "根拠となる数字")
