"""C-1288: the report flattens Markdown in its evidence, like answer and deck.

A fact carrying Markdown printed 「## 概況」 raw inside a bullet, a bold/link
survived, and a table collapsed to a run of 「| --- |」 bars. The report now runs
evidence through evidence.plain_text: decoration becomes prose, a table reads as
「セル / セル；」, and every figure survives.
"""

from __future__ import annotations

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_evidence_plain_text import (
    evaluate_document_evidence_plain_text,
)


def _known(md: str) -> str:
    return md.split("## わかっていること", 1)[1].split("## まだ", 1)[0]


def test_document_evidence_plain_text_eval_passes():
    result = evaluate_document_evidence_plain_text()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_markdown_decoration_does_not_leak_into_bullets():
    facts = [
        Fact(text="## 概況\n登録は **1,240 件** で [詳細](https://example.com/r) を参照。",
             source="r:docs/a.md"),
        Fact(text="| 指標 | 値 |\n| --- | --- |\n| 率 | 63% |", source="r:docs/b.md"),
    ]
    doc = generate_document("新機能ローンチの分析レポートを作って", facts=facts)
    section = _known(doc.markdown)
    for token in ("##", "**", "](", "| ---"):
        assert token not in section, token
    assert "1,240" in section and "63%" in section
    assert validate_document(doc, facts)["usable"]


def test_plain_fact_is_unchanged():
    fact = Fact(text="登録は初週で 1,240 件に達した。", source="r:docs/a.md")
    doc = generate_document("新機能ローンチの分析レポートを作って", facts=[fact])
    assert "登録は初週で 1,240 件に達した。" in _known(doc.markdown)
