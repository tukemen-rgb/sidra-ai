"""C-1242: a report lists an identical fact once, merging its sources.

When the same passage lived in two files, 「わかっていること」 showed the identical
sentence twice with different sources. The report now merges identical-text facts
into one bullet whose 「出典」 names every file; distinct facts and the empty case
are unchanged.
"""

from __future__ import annotations

from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.document_dedupes_identical_facts import (
    evaluate_document_dedupes_identical_facts,
)


def _known(md: str) -> str:
    return md.split("## わかっていること", 1)[1].split("## まだ", 1)[0]


def test_document_dedupe_eval_passes():
    result = evaluate_document_dedupes_identical_facts()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_identical_facts_merge_sources_into_one_bullet():
    dup = "要判断の項目は人が決めるまで着手しない。"
    md = generate_document(
        "方針レポートを作って",
        facts=[Fact(dup, "repo docs/TODO.md"), Fact(dup, "repo docs/cycle.md")],
    ).markdown
    known = _known(md)
    assert known.count(dup) == 1
    assert "TODO.md" in known and "cycle.md" in known


def test_distinct_facts_not_merged():
    md = generate_document(
        "レポートを作って",
        facts=[Fact("事実A。", "repo a.md"), Fact("事実B。", "repo b.md")],
    ).markdown
    known = _known(md)
    assert "事実A。" in known and "事実B。" in known
    assert known.count("- ") == 2
