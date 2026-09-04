"""C-1238: a refused question reads in Japanese, not English audit text.

The gate's English audit reason still fills the API reason field (for consumers
and the audit trail), but the web page and the CLI now show a Japanese message
chosen by security.decision: a gate refusal asks the user to rephrase, any
other refusal asks them to retry. The raw English reason is not shown.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from sidra_ai.api.ask_cli import render
from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.refusal_reason_japanese import evaluate_refusal_reason_japanese

_ENGLISH = "prompt-injection patterns detected; content remains DATA"


def _cli(payload: dict) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        render(payload)
    return out.getvalue()


def test_refusal_reason_japanese_eval_passes():
    result = evaluate_refusal_reason_japanese()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_cli_gate_refusal_is_japanese_not_english():
    out = _cli({
        "answer": "", "refused": True, "reason": _ENGLISH,
        "security": {"decision": "quarantine"}, "citations": [],
    })
    assert "言い換え" in out
    assert _ENGLISH not in out


def test_cli_other_refusal_asks_retry():
    out = _cli({
        "answer": "", "refused": True, "reason": "model backend unavailable",
        "security": {"decision": "allow"}, "citations": [],
    })
    assert "もう一度" in out
    assert "model backend unavailable" not in out


def test_web_page_branches_on_decision_without_raw_reason():
    assert ".decision" in ASK_PAGE
    assert "言い換え" in ASK_PAGE
    assert "result.reason" not in ASK_PAGE
