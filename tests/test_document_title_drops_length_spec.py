"""C-1822: a generated document's title drops a requested length specifier.

「3ページのレポートを作って」 titled the report 「3ページ」 and then failed its body
number-check on the 3 - a length is not a subject. The title now peels a leading
length specifier (digits + ページ/頁/字/文字/枚, closed by の or the end), so the
report falls to a real subject or the default title, while a number that is part
of a real subject (第3四半期, 3年計画, G3) survives.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.documents import generate_document
from sidra_ai.evals.document_title_drops_length_spec import (
    evaluate_document_title_drops_length_spec,
)


def test_document_length_title_eval_passes():
    result = evaluate_document_title_drops_length_spec()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("3ページのレポートを作って", "レポート"),
        ("10ページのレポートを作って", "レポート"),
        ("2000字のレポートを作って", "レポート"),
        ("3ページの競合分析のレポートを作って", "競合分析"),
        ("5枚の売上のレポートを作って", "売上"),
    ],
)
def test_length_specifiers_are_dropped(request_text, expected):
    doc = generate_document(request_text)
    assert doc.title == expected
    # the confusing number must not survive as an unsourced body number
    assert "numbers not present in the evidence" not in (doc.title or "")


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("第3四半期のレポートを作って", "第3四半期"),
        ("3年計画のレポートを作って", "3年計画"),
        ("G3のレポートを作って", "G3"),
        ("5枚組の写真集のレポートを作って", "5枚組の写真集"),
        ("300万円の予算のレポートを作って", "300万円の予算"),
        ("競合分析のレポートを作って", "競合分析"),
    ],
)
def test_numbers_in_real_subjects_survive(request_text, expected):
    assert generate_document(request_text).title == expected
