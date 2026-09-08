"""C-1484: a generated document's title drops a requested file-format word.

The document twin of the deck C-1465. 「売上のレポートをWordで作って」 titled
「売上のレポートをWord」 because the tail-anchored kind strip could not reach a
kind word pushed off the tail by the trailing 「…をWordで」. The title now peels a
format word that sits right after を/の - which キーワード/パスワード never satisfy,
so the subject survives.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.documents import generate_document
from sidra_ai.evals.document_title_drops_format_words import (
    evaluate_document_title_drops_format_words,
)


def test_document_format_title_eval_passes():
    result = evaluate_document_title_drops_format_words()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("売上のレポートをWordで作って", "売上"),
        ("競合分析をPDFでまとめて", "競合分析"),
        ("月次のレポートをdocxで作って", "月次"),
        ("予算表をエクセルで作って", "予算表"),
        ("計画の報告書をPDFで作って", "計画"),
    ],
)
def test_format_words_are_dropped(request_text, expected):
    doc = generate_document(request_text)
    assert doc.title == expected
    # the heading must carry the subject, not the format word
    assert doc.title in doc.markdown


@pytest.mark.parametrize(
    "request_text, expected",
    [
        # subjects that END in ワード: the ー before ワード (not を/の) is why the
        # strip is lookbehind-gated - a bare tail anchor would peel キー / パス.
        ("キーワードのレポートを作って", "キーワード"),
        ("パスワードの資料を作って", "パスワード"),
        # a format word that is itself the subject (mid-phrase or followed by の).
        ("Wordの使い方のレポートを作って", "Wordの使い方"),
        ("エクセル関数の解説をまとめて", "エクセル関数の解説"),
        ("競合分析のレポートを作って", "競合分析"),
    ],
)
def test_format_words_as_subject_are_kept(request_text, expected):
    assert generate_document(request_text).title == expected
