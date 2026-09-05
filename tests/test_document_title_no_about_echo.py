"""C-1255: a report's title drops the 「について」/「に関する」 the request used.

「広告方針についてのレポートを作って」 titled the report 「広告方針について」 and the
概要 said 「『広告方針について』について」. The about phrase is dropped from the
title now, while a request without one is unchanged and a mid-phrase 「について」
inside the subject is kept.
"""

from __future__ import annotations

from sidra_ai.creation.documents import _title_from, generate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_title_no_about_echo import (
    evaluate_document_title_no_about_echo,
)


def test_document_title_no_about_echo_eval_passes():
    result = evaluate_document_title_no_about_echo()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_about_phrase_dropped_from_title():
    assert _title_from("広告方針についてのレポートを作って") == "広告方針"
    assert _title_from("売上に関するレポートを作って") == "売上"
    assert _title_from("新機能についてのドキュメントを作って") == "新機能"
    assert _title_from("採用に関するまとめを作って") == "採用"


def test_non_about_and_bare_unchanged():
    assert _title_from("競合分析のレポートを作って") == "競合分析"  # C-1246 still holds
    assert _title_from("新機能を作って") == "新機能"
    assert _title_from("レポートを作って") == "レポート"  # bare fallback


def test_mid_phrase_about_is_kept():
    assert _title_from("AIについての誤解の分析を作って") == "AIについての誤解の分析"


def test_overview_says_subject_once():
    facts = [Fact("広告は第三者 JS を使わない。", "tukemen-rgb/site docs/ads.md")]
    md = generate_document("広告方針についてのレポートを作って", facts=facts).markdown
    assert "# 広告方針\n" in md
    assert "「広告方針」について" in md
    assert "広告方針について」について" not in md
