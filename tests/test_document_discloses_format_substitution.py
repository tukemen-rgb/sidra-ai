"""C-1834: a document says when it could not make the requested file format.

The document twin of the deck's C-1465. 「レポートをWordで作って」 produced Markdown
and named only Markdown; the summary now names the requested Word/PDF/Excel and
that it could not be made, and stays silent when no format was named or the
format word is the subject.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.document_discloses_format_substitution import (
    _NOTE,
    _service,
    _summary,
    evaluate_document_discloses_format_substitution,
)


def test_format_substitution_eval_passes():
    result = evaluate_document_discloses_format_substitution()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


@pytest.mark.parametrize(
    "request_text, label",
    [
        ("売上のレポートをWordで作って", "Word"),
        ("売上のレポートをPDFで作って", "PDF"),
        ("売上のレポートをExcelで作って", "Excel"),
    ],
)
def test_named_format_is_disclosed(request_text, label):
    s = _summary(_service(), request_text)
    assert _NOTE in s and label in s


@pytest.mark.parametrize(
    "request_text",
    [
        "売上のレポートを作って",
        "PDFで管理する方法のレポートを作って",
        "Wordの使い方のレポートを作って",
    ],
)
def test_no_false_substitution_note(request_text):
    assert _NOTE not in _summary(_service(), request_text)
