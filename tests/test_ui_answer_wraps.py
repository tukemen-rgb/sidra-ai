"""C-1214: long unbroken tokens must wrap instead of widening the page.

On an iPhone-sized viewport the answer's citation labels pushed the
document to 401px of a 390px screen, and the browser shrank every glyph to
fit. ``overflow-wrap: anywhere`` on the answer body and status line is the
same call ``.path`` already made for citation lists; ``pre-wrap`` stays so
answers keep their line structure.
"""

from __future__ import annotations

from sidra_ai.evals.ui_answer_wraps import evaluate_ui_answer_wraps


def test_ui_answer_wraps_eval_passes():
    result = evaluate_ui_answer_wraps()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4
