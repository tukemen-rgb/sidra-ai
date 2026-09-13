"""C-1772: the report cover's number-sourcing claim matches what is sourced.

The preamble asserted 「数字はすべて下の出典から」 unconditionally, one line under
a `# ` heading `_title_from` fills from the request - so 「解約率30%の改善レポート」
promised every number was sourced right beside an unsourced 30%. C-1476 disclosed
the gap two sections down, but the cover kept the blanket claim and contradicted
it. The cover now scopes its promise to the body and names the unconfirmed title
number up front; a clean title, or a title number the evidence carries, keeps the
original assurance.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.report_cover_number_claim_matches_its_sourcing import (
    evaluate_report_cover_number_claim_matches_its_sourcing,
)

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
_BLANKET = "数字はすべて下の出典から"
_SECTION3 = "タイトルに含まれる数値は、索引した根拠では確認できませんでした"


def _cover(markdown: str) -> str:
    return next(ln for ln in markdown.splitlines() if ln.startswith("> SIDRA AI"))


def test_report_cover_claim_eval_passes():
    result = evaluate_report_cover_number_claim_matches_its_sourcing()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_unsourced_title_number_scopes_the_cover_and_names_the_gap():
    facts = [Fact("解約率は改善した。", "docs/churn.md")]
    doc = generate_document("解約率30%の改善レポートを作って", facts=facts, now=_NOW)
    cover = _cover(doc.markdown)
    assert _BLANKET not in cover  # no unconditional "all numbers sourced"
    assert "タイトル" in cover and "確認できて" in cover  # names the gap on the cover
    assert _SECTION3 in doc.markdown  # the section-three disclosure still fires
    assert validate_document(doc, facts)["usable"]


def test_clean_title_keeps_the_full_assurance():
    doc = generate_document(
        "競合分析のレポートを作って",
        facts=[Fact("競合Aは値下げした。", "docs/market.md")], now=_NOW,
    )
    assert _BLANKET in _cover(doc.markdown)


def test_a_sourced_title_number_keeps_the_full_assurance():
    doc = generate_document(
        "売上30%増のレポートを作って",
        facts=[Fact("売上は30%伸びた。", "docs/sales.md")], now=_NOW,
    )
    assert _BLANKET in _cover(doc.markdown)
