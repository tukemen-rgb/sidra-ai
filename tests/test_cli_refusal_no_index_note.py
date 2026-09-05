"""C-1254: a safety refusal doesn't blame the index for the missing answer.

sidra-ask refused a prompt-injection input and then printed 「索引に根拠が無いか、
取り込みがまだ走っていない」 - the no-evidence note, which reads as "re-run
ingestion" for a problem ingestion cannot fix. The refusal path omits the index
note now; a genuine no-evidence answer keeps it.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from sidra_ai.api.ask_cli import render
from sidra_ai.evals.cli_refusal_no_index_note import (
    evaluate_cli_refusal_no_index_note,
)

_NOTE = "索引に根拠が無い"


def _render(payload):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = render(payload)
    return buf.getvalue(), code


def test_cli_refusal_no_index_note_eval_passes():
    result = evaluate_cli_refusal_no_index_note()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_refusal_omits_index_note():
    out, code = _render(
        {
            "refused": True,
            "answer": "",
            "security": {"decision": "quarantine"},
            "citations": [],
        }
    )
    assert "拒否" in out
    assert _NOTE not in out
    assert "取り込みがまだ走っていない" not in out
    assert code == 3


def test_no_evidence_answer_keeps_index_note():
    out, code = _render(
        {"refused": False, "answer": "現時点では十分な根拠がありません。", "citations": [], "model": {}}
    )
    assert _NOTE in out
    assert code == 0


def test_refusal_with_citations_still_shows_them():
    out, _ = _render(
        {
            "refused": True,
            "answer": "",
            "security": {"decision": "quarantine"},
            "citations": [{"label": "S1", "citation": "tukemen-rgb/site README.md"}],
        }
    )
    assert "S1" in out and "README.md" in out
    assert _NOTE not in out
