"""C-1483: the report neutralises HTML from a fact, source label, or the request.

The report (.md) was the one HTML-bearing artifact that did not escape fact or
request content, so a <script> from an EXTERNAL-trust Issue/PR body rode through
the index into the document raw. It now escapes the title, fact text and source
labels, so tags display as the literal source text and never execute.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_escapes_html_in_evidence import (
    evaluate_document_escapes_html_in_evidence,
)

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_document_escape_eval_passes():
    result = evaluate_document_escapes_html_in_evidence()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


def test_fact_script_is_escaped_not_raw():
    md = generate_document(
        "セキュリティのレポートを作って",
        facts=[Fact("課題: <script>alert(1)</script> が残る。", "docs/a.md")],
        now=_NOW,
    ).markdown
    assert "<script>" not in md
    assert "&lt;script&gt;" in md  # neutralised, not dropped
    assert "課題:" in md and "が残る" in md  # content preserved


def test_request_title_html_is_escaped():
    md = generate_document(
        "<script>alert(9)</script>のレポートを作って",
        facts=[Fact("普通の課題。", "docs/a.md")], now=_NOW,
    ).markdown
    assert "# <script>" not in md
    assert "「<script>" not in md


def test_source_label_html_is_escaped():
    md = generate_document(
        "レポートを作って",
        facts=[Fact("変更した。", "docs/<img src=x onerror=alert(2)>.md")], now=_NOW,
    ).markdown
    assert "<img src=x onerror" not in md


def test_clean_document_unaffected():
    md = generate_document(
        "競合分析のレポートを作って",
        facts=[Fact("競合Aは値下げした。", "docs/m.md")], now=_NOW,
    ).markdown
    assert "競合Aは値下げした" in md
    assert "&lt;" not in md
