"""C-1232: a report's 概要 does not verbatim-copy the first fact.

「## 概要」 used to be `retrieved[0].text` copied whole, and that same fact
opened 「## わかっていること」 - so the report began with the identical
paragraph twice. 概要 is now an honest framing line; every fact still lists
under わかっていること with its source; an empty report keeps 概要 blank.
"""

from __future__ import annotations

from sidra_ai.creation.documents import BLANK, generate_document, validate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_overview_no_duplicate import (
    evaluate_document_overview_no_duplicate,
)

FACTS = [
    Fact("紹介トラッキングは個人の行動履歴なので既定では計測しない。", "repo docs/a.md"),
    Fact("回答には必ず出典の引用が付く。", "repo docs/b.md"),
]


def _section(md: str, name: str) -> str:
    return md.split(f"## {name}", 1)[1].split("\n## ", 1)[0]


def test_overview_eval_passes():
    result = evaluate_document_overview_no_duplicate()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_overview_does_not_duplicate_first_fact():
    doc = generate_document("方針レポートを作って", facts=FACTS)
    md = doc.markdown
    assert md.count(FACTS[0].text) == 1
    assert FACTS[0].text not in _section(md, "概要")
    assert FACTS[0].text in _section(md, "わかっていること")
    assert FACTS[1].text in _section(md, "わかっていること")
    assert validate_document(doc, FACTS)["usable"]


def test_empty_report_overview_stays_blank():
    doc = generate_document("レポートを作って", facts=[])
    assert "概要" in doc.unfilled
    assert BLANK in _section(doc.markdown, "概要")
