"""C-1838: a deck asked for in a document format names that format, not PowerPoint.

The deck-summary twin of C-1834. 「スライドをPDFで作って」 got the fixed PowerPoint
notice, naming a format the operator never asked for. The summary now names the
requested format (「PDF 形式では作れないため、HTML で保存しています」) and keeps the
.pptx notice only when no document format was named (C-1274).
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.deck_names_requested_format import (
    _DOC_NOTE,
    _PPTX_NOTE,
    _service,
    _summary,
    evaluate_deck_names_requested_format,
)


def test_deck_names_format_eval_passes():
    result = evaluate_deck_names_requested_format()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    "request_text, label",
    [
        ("売上のスライドをPDFで作って", "PDF"),
        ("売上のスライドをWordで作って", "Word"),
        ("売上のスライドをExcelで作って", "Excel"),
    ],
)
def test_named_format_replaces_powerpoint_notice(request_text, label):
    s = _summary(_service(), request_text)
    assert _DOC_NOTE in s and label in s
    assert _PPTX_NOTE not in s


@pytest.mark.parametrize(
    "request_text",
    ["売上のスライドを作って", "売上のスライドをパワポで作って"],
)
def test_plain_or_pptx_deck_keeps_powerpoint_notice(request_text):
    s = _summary(_service(), request_text)
    assert _PPTX_NOTE in s
    assert _DOC_NOTE not in s
