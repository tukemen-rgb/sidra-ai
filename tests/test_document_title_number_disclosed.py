"""C-1476: a report discloses a title figure the evidence does not support.

`_title_from` copies the request's subject onto the cover, so 「解約率30%の改善
レポート」 put 30% in the heading beside 「数字はすべて下の出典から」, where
`validate_document` (body only) could not see it. The report now discloses, in
「まだ埋まっていないこと」, a title number the evidence does not confirm - without
reprinting the digit, and only when the number is absent from every fact and
source label.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact, NUMBER
from sidra_ai.evals.document_title_number_disclosed import (
    evaluate_document_title_number_disclosed,
)

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)
_DISCLOSURE = "タイトルに含まれる数値は、索引した根拠では確認できませんでした"


def test_document_title_number_eval_passes():
    result = evaluate_document_title_number_disclosed()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_unsourced_headline_statistic_is_disclosed_without_reprinting_it():
    facts = [Fact("解約率は改善した。", "docs/churn.md")]
    doc = generate_document("解約率30%の改善レポートを作って", facts=facts, now=_NOW)
    assert _DISCLOSURE in doc.markdown
    line = next(ln for ln in doc.markdown.splitlines() if _DISCLOSURE in ln)
    assert not NUMBER.findall(line)  # the disclosure names no digit
    assert validate_document(doc, facts)["usable"]  # and does not fail validation


def test_title_number_present_in_evidence_is_not_disclosed():
    in_text = generate_document(
        "第3四半期の進捗レポートを作って",
        facts=[Fact("第3四半期は完了した。", "docs/status.md")], now=_NOW,
    )
    assert _DISCLOSURE not in in_text.markdown
    via_label = generate_document(
        "17番の課題レポートを作って",
        facts=[Fact("認証まわりを直した。", "docs/PR-17.md")], now=_NOW,
    )
    assert _DISCLOSURE not in via_label.markdown


def test_title_without_a_number_is_silent():
    doc = generate_document(
        "競合分析のレポートを作って",
        facts=[Fact("競合Aは値下げした。", "docs/market.md")], now=_NOW,
    )
    assert _DISCLOSURE not in doc.markdown
