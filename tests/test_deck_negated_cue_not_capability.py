"""C-1461: a negated fact is kept off the deck's capability slide.

「対応」 matched inside 「未対応」, so 「未対応の不具合」 was shown under いま出来ること (a
problem as a capability). A cue preceded by 未/非/不 no longer counts for the
positive section it stands for, and 完了/実装/リリース/済 route completed work.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.decks import _matches
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_negated_cue_not_capability import (
    evaluate_deck_negated_cue_not_capability,
)


def _f(text: str) -> Fact:
    return Fact(text=text, source="r:x")


def test_deck_negated_cue_eval_passes():
    result = evaluate_deck_negated_cue_not_capability()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    "text",
    ["未対応の不具合が残っている。", "通知機能が未実装のまま残っている。"],
)
def test_negated_fact_off_capability_slide(text):
    assert not _matches("いま出来ること", _f(text))
    assert _matches("残っていること", _f(text))


def test_unresolved_is_not_solved():
    assert not _matches("解決", _f("課題は未解決である。"))


@pytest.mark.parametrize(
    "text",
    ["決済連携の実装は完了した。", "検索機能に対応した。", "新機能をリリース済み。"],
)
def test_completed_work_is_a_capability(text):
    assert _matches("いま出来ること", _f(text))
