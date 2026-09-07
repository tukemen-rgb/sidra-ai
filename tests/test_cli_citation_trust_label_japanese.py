"""C-1469: the CLI renders a citation's trust level in Japanese, not a raw enum.

An issue/PR-grounded citation (EXTERNAL by ingestion) rendered as 「(external)」
beside the Japanese redaction marks. The level is now a Japanese label;
internal_repo stays suppressed and an unknown value falls back to raw.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from sidra_ai.api import ask_cli
from sidra_ai.evals.cli_citation_trust_label_japanese import (
    evaluate_cli_citation_trust_label_japanese,
)


def _cite_line(payload) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ask_cli.render(payload)
    seen_header = False
    for line in buf.getvalue().splitlines():
        if line.startswith("引用:"):
            seen_header = True
            continue
        if seen_header and line.strip().startswith("[S1]"):
            return line
    return ""


def _payload(**citation):
    return {
        "refused": False,
        "answer": "回答本文。",
        "citations": [{"label": "S1", "citation": "r@a:issues/42", **citation}],
        "model": {"backend": "echo"},
    }


def test_cli_trust_label_eval_passes():
    result = evaluate_cli_citation_trust_label_japanese()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    "level, jp",
    [("external", "外部"), ("unverified", "未検証"), ("operator", "運用者"), ("system", "システム")],
)
def test_trust_level_shown_in_japanese(level, jp):
    line = _cite_line(_payload(trust_level=level))
    assert jp in line
    assert level not in line


def test_internal_repo_has_no_trust_mark():
    assert "(" not in _cite_line(_payload(trust_level="internal_repo"))


def test_redaction_mark_and_trust_label_coexist():
    line = _cite_line(_payload(trust_level="external", redacted=True))
    assert "一部秘匿" in line and "外部" in line


def test_unknown_trust_level_falls_back_to_raw():
    assert "someday" in _cite_line(_payload(trust_level="someday"))
