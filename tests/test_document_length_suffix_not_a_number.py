"""C-1842: a page count behind the subject is a length, not a title or a figure.

The suffix half of C-1822. 「サイトについてのドキュメントを3ページで作って」 titled
「…を3ページ」, and the 「3」 - a page count with no evidence - then failed the
document number-check, telling the reader their report 「検証に落ちています」. The
length now falls away from the title from either side; a subject number and a real
headline statistic are untouched.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.evals.document_length_suffix_not_a_number import (
    evaluate_document_length_suffix_not_a_number,
)


def test_document_length_eval_passes():
    result = evaluate_document_length_suffix_not_a_number()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("サイトについてのドキュメントを3ページで作って", "サイト"),
        ("競合分析のレポートを5ページで作成して", "競合分析"),
        ("売上のレポートを2000字で書いて", "売上"),
        ("3ページのレポートを作って", "レポート"),
    ],
)
def test_length_spec_stripped_from_title(request_text, expected):
    assert generate_document(request_text, facts=[]).title == expected


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("第3四半期のレポートを作って", "第3四半期"),
        ("5枚組の写真集のレポートを作って", "5枚組の写真集"),
    ],
)
def test_subject_number_survives(request_text, expected):
    assert generate_document(request_text, facts=[]).title == expected


def test_requested_page_count_does_not_fail_verification():
    document = generate_document(
        "サイトについてのドキュメントを3ページで作って",
        facts=[],
        subject_unmatched=True,
    )
    verdict = validate_document(document, [])
    assert verdict["usable"] is True
    assert "3" not in "".join(verdict["failures"])


def test_real_headline_statistic_still_fails():
    document = generate_document(
        "解約率30%の改善レポートを作って", facts=[], subject_unmatched=True
    )
    assert validate_document(document, [])["usable"] is False
