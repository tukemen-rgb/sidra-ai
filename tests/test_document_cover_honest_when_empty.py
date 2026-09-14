"""C-1803: an empty report's cover must not promise sourced numbers.

When the index returns nothing and the title has no number, the body is all
〔社長が埋める欄〕 and the 「出典」 section says none were found - but the cover
still read 「数字はすべて下の出典から」. Reopened alone it looked like a normal
sourced report. The cover now states the empty, no-evidence truth and promises
no sourcing; a genuinely sourced cover, and C-1772's title-number disclosure,
are untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_cover_honest_when_empty import (
    evaluate_document_cover_honest_when_empty,
)

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _cover(markdown: str) -> str:
    return next(ln for ln in markdown.splitlines() if ln.startswith(">"))


def test_document_cover_empty_eval_passes():
    result = evaluate_document_cover_honest_when_empty()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_empty_draft_cover_makes_no_sourcing_promise():
    doc = generate_document("所有権についてレポートを書いて", facts=[], now=_NOW)
    cover = _cover(doc.markdown)
    assert "下の出典から" not in cover
    assert "索引にこの依頼の根拠が無く" in cover


def test_sourced_cover_keeps_its_promise():
    doc = generate_document(
        "進捗レポートを書いて", facts=[Fact("完了は 42 件。", "docs/s.md")], now=_NOW
    )
    assert "数字はすべて下の出典から" in _cover(doc.markdown)


def test_empty_numbered_title_still_discloses_the_gap():
    doc = generate_document("2025年度の計画レポートを書いて", facts=[], now=_NOW)
    assert "タイトルの数値は索引した根拠では確認できていません" in _cover(doc.markdown)
