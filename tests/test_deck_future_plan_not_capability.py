"""C-1474: a deck keeps planned/future work off the current-capability slide.

「次はモバイル対応を予定している」 was placed under 「いま出来ること」/「解決」 via the
「対応」 cue - a plan shown as a shipped capability. A future marker now routes such
a fact to the forward-looking slide (残っていること / 次の一歩).
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_future_plan_not_capability import (
    evaluate_deck_future_plan_not_capability,
)


def _placement(request, facts, outline):
    deck = generate_deck(request, facts=facts, outline=outline)
    return {s.title: [b for b in s.bullets] for s in deck.slides}


def test_deck_future_plan_eval_passes():
    result = evaluate_deck_future_plan_not_capability()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize("text", ["次はモバイル対応を予定している。", "今後は多言語対応を進める。", "これから決済基盤を提供する。"])
def test_status_future_plan_on_forward_slide(text):
    p = _placement("週次進捗のスライドを作って", [Fact(text, "r")], "status")
    assert not any(text[:8] in b for b in p["いま出来ること"])
    assert any(text[:8] in b for b in p["残っていること"])


def test_pitch_future_plan_on_next_step():
    text = "次はモバイル対応を予定している。"
    p = _placement("提案のスライドを作って", [Fact(text, "r")], "pitch")
    assert not any(text[:8] in b for b in p["解決"])
    assert any(text[:8] in b for b in p["次の一歩"])


def test_shipped_capability_unchanged():
    text = "決済連携の実装は完了し、本番に投入した。"
    p = _placement("週次進捗のスライドを作って", [Fact(text, "r")], "status")
    assert any(text[:8] in b for b in p["いま出来ること"])
