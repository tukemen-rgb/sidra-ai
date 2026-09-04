"""C-1237: a generated deck puts each fact on only one slide.

build_slides filled every section from the whole fact list, so a fact matching
two sections' cues showed on several slides at once - the deck twin of the
report's 概要 duplication (C-1232). Each fact is now claimed by the first
section that takes it; a later slide with nothing of its own keeps its blank.
"""

from __future__ import annotations

import re

from sidra_ai.creation.decks import BLANK, generate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_no_duplicate_facts import evaluate_deck_no_duplicate_facts


def _slide_texts(deck):
    return [" ".join(s.bullets) for s in deck.slides]


def test_deck_no_duplicate_facts_eval_passes():
    result = evaluate_deck_no_duplicate_facts()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_dual_matching_fact_appears_once():
    facts = [
        Fact("検査エンジンは 3 種類の圧縮を展開できる。", "repo docs/a.md"),
        Fact("次の一歩は 5 件のテンプレートを追加すること。", "repo docs/b.md"),
    ]
    texts = _slide_texts(generate_deck("紹介スライドを作って", facts=facts))
    for fact in facts:
        assert sum(1 for t in texts if fact.text in t) == 1
        assert any(fact.text in t for t in texts)


def test_empty_deck_stays_blank():
    texts = _slide_texts(generate_deck("紹介スライドを作って", facts=[]))
    assert all(BLANK in t for t in texts)
    assert not any(re.search(r"\d", t) for t in texts)
