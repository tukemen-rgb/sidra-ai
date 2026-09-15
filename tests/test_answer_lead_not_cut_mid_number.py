"""C-1852: the answer body does not end inside a number at its 400-char cap.

The answer-body member of the truncation-honesty family (C-1849 citation excerpt,
C-1851 deck bullet, C-1217 report body). The echo lead caps at 400 chars and marks
overflow with 「...」, but the cut landed mid-digit: a long answer whose figure
straddles the cap showed 「…1,23...」 — a partial number reading as a small whole
value. A split figure is now dropped back to its start; a whole figure at the cap
is kept and the 「...」 still marks the overflow.
"""

from __future__ import annotations

from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.evals.answer_lead_not_cut_mid_number import (
    evaluate_answer_lead_not_cut_mid_number,
)

_MODEL = EchoModelAdapter()
_NUMBER_CHARS = frozenset("0123456789０１２３４５６７８９,，.．")
_PAD = "あ" * 396


def _lead(content: str) -> str:
    return _MODEL._lead(content, "売上")


def test_answer_lead_eval_passes():
    result = evaluate_answer_lead_not_cut_mid_number()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_straddling_figure_not_shown_partially():
    lead = _lead("売上" + _PAD + "1,234,567,890" + "円" + "あ" * 20)
    assert lead.endswith("...")
    assert not (len(lead) >= 4 and lead[-4] in _NUMBER_CHARS)
    assert "売上" in lead


def test_whole_figure_before_cut_is_kept():
    lead = _lead("売上" + "あ" * 390 + "は42と" + "ん" * 16)
    assert "42" in lead


def test_uncapped_lead_is_untouched():
    lead = _lead("売上は 1,234,567 円。")
    assert "..." not in lead
    assert "1,234,567" in lead
