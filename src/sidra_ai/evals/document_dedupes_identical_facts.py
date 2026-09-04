"""Does a report list an identical fact once, not once per source file?

C-1242: when the same passage lives in two files (a TODO copied into another
doc), generate_document emitted a bullet for each, so 「わかっていること」 showed
the identical sentence twice with different sources - the reader reads it twice.
The report now collapses identical-text facts into one bullet whose 「出典」 lists
every file that carries it, so the shared text is stated once while "both files
say this" is preserved (the same choice as the answer's C-1241 dedupe).

The checks build a document from two identical-text facts plus a distinct one
and confirm the shared text appears once, both sources are named on it, the
distinct fact keeps its own bullet, and an empty retrieval still blanks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentDedupeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _known_section(markdown: str) -> str:
    return markdown.split("## わかっていること", 1)[1].split("## まだ", 1)[0]


def evaluate_document_dedupes_identical_facts() -> DocumentDedupeResult:
    from sidra_ai.creation.documents import BLANK, generate_document
    from sidra_ai.creation.evidence import Fact

    checks = 0
    failures: list[str] = []

    dup = "要判断の項目は人が決めるまで着手しない方針である。"
    distinct = "回答には必ず出典の引用が付く。"
    doc = generate_document(
        "方針レポートを作って",
        facts=[
            Fact(dup, "repo docs/TODO.md"),
            Fact(dup, "repo docs/cycle.md"),
            Fact(distinct, "repo docs/arch.md"),
        ],
    )
    known = _known_section(doc.markdown)

    # 1: the shared text appears once, not once per file.
    if known.count(dup) == 1:
        checks += 1
    else:
        failures.append(f"the shared fact appears {known.count(dup)}x (expected 1)")

    # 2-3: both source files are still named on the merged bullet.
    if "TODO.md" in known:
        checks += 1
    else:
        failures.append("first source dropped from the merged bullet")
    if "cycle.md" in known:
        checks += 1
    else:
        failures.append("second source dropped from the merged bullet")

    # 4: the distinct fact keeps its own bullet.
    if distinct in known:
        checks += 1
    else:
        failures.append("the distinct fact vanished")

    # 5: exactly three source citations survive across two bullets (2 merged + 1).
    if known.count("docs/") == 3:
        checks += 1
    else:
        failures.append(f"expected 3 source labels, found {known.count('docs/')}")

    # 6: two DISTINCT facts are not merged (no false dedupe).
    two = generate_document(
        "レポートを作って",
        facts=[Fact("事実A。", "repo a.md"), Fact("事実B。", "repo b.md")],
    )
    kn = _known_section(two.markdown)
    if "事実A。" in kn and "事実B。" in kn and kn.count("- ") == 2:
        checks += 1
    else:
        failures.append("distinct facts were wrongly merged")

    # 7-8: an empty retrieval still blanks honestly.
    empty = generate_document("レポートを作って", facts=[])
    if "概要" in empty.unfilled:
        checks += 1
    else:
        failures.append("empty report: 概要 not unfilled")
    if BLANK in _known_section(empty.markdown):
        checks += 1
    else:
        failures.append("empty report: わかっていること not blank")

    return DocumentDedupeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=8,
        failures=tuple(failures),
    )
