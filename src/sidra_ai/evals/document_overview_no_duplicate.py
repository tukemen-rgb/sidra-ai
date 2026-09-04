"""Does a report's 概要 avoid verbatim-copying the first fact?

C-1232: 「## 概要」 was `retrieved[0].text` copied whole, and the same fact
then opened 「## わかっていること」 as its first bullet - so a generated report
began with the identical paragraph printed twice. Beyond looking broken, a
「概要」 that is only the first retrieved fact is not a summary; calling it one
is the kind of overclaim this project refuses elsewhere.

The fix keeps 「わかっていること」 listing every fact with its source, makes
「概要」 an honest framing line (no fact copy, no digit), leaves the empty
report's 「概要」 blank so the C-1128 empty-notice still fires, and keeps the
number-fabrication validator green.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentOverviewResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _section(markdown: str, name: str) -> str:
    """The text of one 「## <name>」 section, up to the next 「## 」."""
    marker = f"## {name}"
    if marker not in markdown:
        return ""
    after = markdown.split(marker, 1)[1]
    return after.split("\n## ", 1)[0]


def evaluate_document_overview_no_duplicate() -> DocumentOverviewResult:
    from sidra_ai.creation.documents import (
        BLANK,
        generate_document,
        validate_document,
    )
    from sidra_ai.creation.evidence import Fact

    checks = 0
    failures: list[str] = []

    facts = [
        Fact("紹介トラッキングは個人の行動履歴なので既定では計測しない方針。", "repo docs/a.md"),
        Fact("回答には必ず出典の引用が付く。", "repo docs/b.md"),
    ]
    doc = generate_document("リトライ方針のドキュメントを作って", facts=facts)
    md = doc.markdown
    overview = _section(md, "概要")
    known = _section(md, "わかっていること")
    first = facts[0].text

    # 1: 概要 section is present and not empty.
    if overview.strip():
        checks += 1
    else:
        failures.append("概要 section empty")

    # 2: 概要 does not verbatim-copy the first fact (the bug).
    if first not in overview:
        checks += 1
    else:
        failures.append("概要 still copies the first fact verbatim")

    # 3-4: every fact is still listed under わかっていること with its source.
    if first in known:
        checks += 1
    else:
        failures.append("first fact missing from わかっていること")
    if facts[1].text in known:
        checks += 1
    else:
        failures.append("second fact missing from わかっていること")

    # 5: the first fact appears exactly once in the whole document.
    if md.count(first) == 1:
        checks += 1
    else:
        failures.append(f"first fact appears {md.count(first)}x (expected 1)")

    # 6: 概要 carries no digit - the fabrication validator scans the body.
    if not any(ch.isdigit() for ch in overview):
        checks += 1
    else:
        failures.append("概要 contains a digit")

    # 7: the document still validates (numbers all sourced, sections present).
    if validate_document(doc, facts)["usable"]:
        checks += 1
    else:
        failures.append("document failed validation")

    # 8-9: an empty retrieval keeps 概要 blank and unfilled (C-1128 relies on it).
    empty = generate_document("レポートを作って", facts=[])
    if "概要" in empty.unfilled:
        checks += 1
    else:
        failures.append("empty report: 概要 not marked unfilled")
    if BLANK in _section(empty.markdown, "概要"):
        checks += 1
    else:
        failures.append("empty report: 概要 has no blank")

    # 10: a single-fact report shows that fact once and does not copy it into 概要.
    one = generate_document("レポートを作って", facts=[facts[0]])
    if one.markdown.count(first) == 1 and first not in _section(one.markdown, "概要"):
        checks += 1
    else:
        failures.append("single-fact report duplicates or copies the fact into 概要")

    return DocumentOverviewResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=10,
        failures=tuple(failures),
    )
