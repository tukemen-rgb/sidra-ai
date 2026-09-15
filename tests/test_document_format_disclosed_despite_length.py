"""C-1844: a length after the format word must not hide the format.

The word-order re-opening of C-1834. 「サイトのレポートをWordで3ページで作って」 made
requested_format return "", so the 「Word 形式では作れない」 disclosure never fired and
a reader who asked for Word got Markdown silently. The format is now found from
either order; a format word that names the subject still returns "". Both the
document and the deck gate their disclosure on this one function (C-1834/C-1838).
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.documents import requested_format
from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.document_format_disclosed_despite_length import (
    evaluate_document_format_disclosed_despite_length,
)


def test_format_disclosed_eval_passes():
    result = evaluate_document_format_disclosed_despite_length()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("サイトのレポートをWordで3ページで作って", "Word"),
        ("競合分析のレポートを3ページでPDFで作成して", "PDF"),
        ("売上のレポートをExcelで2000字でまとめて", "Excel"),
        ("企画書をワードで5ページでまとめて", "Word"),
        ("サイトのレポートをWordで作って", "Word"),
    ],
)
def test_format_found_with_or_without_trailing_length(request_text, expected):
    assert requested_format(request_text) == expected


@pytest.mark.parametrize(
    "request_text",
    [
        "Wordの使い方のレポートを作って",
        "PDFで管理する方法のレポートを作って",
        "パスワードのレポートを作って",
        "キーワードを3つ作って",
        "売上のレポートを作って",
    ],
)
def test_no_format_stays_empty(request_text):
    assert requested_format(request_text) == ""


def test_deck_summary_names_format_despite_trailing_length(tmp_path):
    generate = build_deck_generator(tmp_path)
    ask = "売上のスライドをPDFで3枚で作って"
    outcome = generate(ask, detect_creation_intent(ask), [])
    assert "PDF 形式では作れない" in outcome.summary
