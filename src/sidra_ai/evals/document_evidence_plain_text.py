"""Does the report flatten Markdown in its evidence, like the answer and deck?

C-1288: the answer path (echo ``_lead``) and the deck run retrieved evidence
through ``evidence.plain_text``; the report did not. A fact carrying Markdown
printed 「## 概況」 raw inside a bullet, a bold/link survived as 「**…**」/
「[…](url)」, and a table collapsed to one unreadable run of 「| --- |」 bars when
the whitespace join ate its newlines. The report now flattens the same way:
decoration becomes prose, a table reads as 「セル / セル；」, and every word and
number survives so the fabrication check still sees the figures.
"""

from __future__ import annotations

from dataclasses import dataclass

_REQUEST = "新機能ローンチの分析レポートを作って"


def _facts():
    from sidra_ai.creation.evidence import Fact

    return [
        Fact(text="## 概況\n登録は **1,240 件** で [詳細](https://example.com/r) を参照。",
             source="r:docs/a.md"),
        Fact(text="| 指標 | 値 |\n| --- | --- |\n| 率 | 63% |", source="r:docs/b.md"),
    ]


@dataclass(frozen=True)
class DocumentEvidencePlainResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _known_section(markdown: str) -> str:
    if "## わかっていること" not in markdown or "## まだ" not in markdown:
        return ""
    return markdown.split("## わかっていること", 1)[1].split("## まだ", 1)[0]


def evaluate_document_evidence_plain_text() -> DocumentEvidencePlainResult:
    from sidra_ai.creation.documents import generate_document, validate_document

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    facts = _facts()
    doc = generate_document(_REQUEST, facts=facts)
    section = _known_section(doc.markdown)
    add(bool(section), "the report is missing its 「わかっていること」 section")

    # 1: no raw Markdown decoration leaks into the bullets.
    add("##" not in section, "a raw heading 「##」 leaked into a bullet")
    add("**" not in section, "raw bold 「**」 leaked into a bullet")
    add("](" not in section, "a raw Markdown link 「](url)」 leaked into a bullet")
    add("| ---" not in section, "a raw table separator 「| --- |」 leaked into a bullet")

    # 2: the flatten keeps the content - the words and every figure survive, so
    #    the report is not quietly shorter than its evidence and the fabrication
    #    validator still sees the numbers it checks.
    add("1,240" in section and "63%" in section, "a figure was lost in the flatten")
    add(validate_document(doc, facts)["usable"],
        "the report failed validation after the flatten")

    # 3: the table became prose rather than bars - a flattened row marker shows.
    add("／" in section or " / " in section or "；" in section,
        "the table was not flattened to prose")

    total = 8
    return DocumentEvidencePlainResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DocumentEvidencePlainResult",
    "evaluate_document_evidence_plain_text",
]
