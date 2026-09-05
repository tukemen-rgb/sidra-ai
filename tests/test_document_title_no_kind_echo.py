"""C-1246: a report's title is the subject, not subject + 「レポート」.

「競合分析のレポートを作って」 titled the report 「競合分析のレポート」, so the
kind word doubled in the heading, the 概要 and the confirmation. The trailing
document-kind word is dropped from the title now, while a request without one is
left alone and a bare 「レポートを作って」 keeps its fallback.
"""

from __future__ import annotations

from sidra_ai.creation.documents import _title_from, generate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_title_no_kind_echo import (
    evaluate_document_title_no_kind_echo,
)


def test_document_title_no_kind_echo_eval_passes():
    result = evaluate_document_title_no_kind_echo()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_kind_word_dropped_from_title():
    assert _title_from("競合分析のレポートを作って") == "競合分析"
    assert _title_from("売上の資料を作って") == "売上"
    assert _title_from("月次まとめを作って") == "月次"
    assert _title_from("計画のドキュメントを作成して") == "計画"


def test_non_kind_title_unchanged():
    assert _title_from("競合分析を作って") == "競合分析"
    # A subject that merely contains a kind word mid-phrase is not stripped.
    assert _title_from("企画書のレビューを作って") == "企画書のレビュー"


def test_bare_kind_word_keeps_fallback():
    assert _title_from("レポートを作って") == "レポート"
    assert _title_from("資料を作って") == "資料"


def test_overview_and_heading_say_the_subject_once():
    facts = [Fact("競合は 3 社。", "tukemen-rgb/site docs/competitive-analysis.md")]
    md = generate_document("競合分析のレポートを作って", facts=facts).markdown
    assert "# 競合分析\n" in md
    assert "「競合分析」について" in md
    assert "競合分析のレポート」" not in md
