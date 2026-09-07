"""C-1467: a generated document's title drops the deliverable-kind word it is.

The document twin of the deck C-1465, plus the C-1458 follow-through: the eight
deliverable words C-1458 routed to DOCUMENT (報告書/議事録/マニュアル/…) were never
stripped from the title, and stacked kind/about phrases left the inner word.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.documents import generate_document
from sidra_ai.evals.document_title_drops_kind_words import (
    evaluate_document_title_drops_kind_words,
)


def test_document_title_eval_passes():
    result = evaluate_document_title_drops_kind_words()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 14


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("会議の議事録を作って", "会議"),
        ("新機能の報告書を作って", "新機能"),
        ("操作マニュアルを作って", "操作"),
        ("システムの要件定義書を作って", "システム"),
        ("競合分析のレポートをドキュメントで作って", "競合分析"),
        ("広告方針に関する報告書を作って", "広告方針"),
    ],
)
def test_kind_words_are_dropped(request_text, expected):
    doc = generate_document(request_text)
    assert doc.title == expected
    # the heading must not print the deliverable's own kind
    assert doc.title in doc.markdown


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("競合分析のレポートを作って", "競合分析"),
        ("セキュリティ方針についてのレポートを作って", "セキュリティ方針"),
        ("報告書フォーマットの提案書を作って", "報告書フォーマット"),
        ("議事録を作って", "議事録"),
        ("レポートを作って", "レポート"),
    ],
)
def test_existing_titles_unchanged(request_text, expected):
    assert generate_document(request_text).title == expected
