"""C-1289: the deck flattens Markdown in its slide bullets, like answer/report.

``_bullets_for`` trimmed evidence to whole sentences but never ran it through
plain_text, so a fact carrying 「## 概況」 or a table put raw 「##」/「| --- |」 on an
HTML slide as literal characters. The deck now flattens first.
"""

from __future__ import annotations

import re

from sidra_ai.creation.decks import generate_deck, validate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_evidence_plain_text import evaluate_deck_evidence_plain_text

_REQUEST = "新機能ローンチの週次進捗のプレゼン資料を作って"


def _facts():
    return [
        Fact(text="## 概況\n登録は **1,240 件** で [詳細](https://example.com/r) を参照。",
             source="r:docs/a.md"),
        Fact(text="| 指標 | 値 |\n| --- | --- |\n| 率 | 63% |", source="r:docs/b.md"),
    ]


def test_deck_evidence_plain_text_eval_passes():
    result = evaluate_deck_evidence_plain_text()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_markdown_decoration_does_not_reach_slides():
    deck = generate_deck(_REQUEST, facts=_facts())
    for token in ("##", "**", "](", "| ---"):
        assert token not in deck.html, token
    assert "1,240" in deck.html and "63%" in deck.html
    assert validate_deck(deck, _facts())["usable"]


def test_plain_fact_bullet_is_unchanged():
    fact = Fact(text="登録は初週で 1,240 件に達した。", source="r:docs/a.md")
    deck = generate_deck(_REQUEST, facts=[fact])
    assert "登録は初週で 1,240 件に達した。" in deck.html
