"""Does the report cover's number-sourcing claim match what is actually sourced?

C-1772. The report preamble made the same promise the body validator enforces -
「数字はすべて下の出典から」 (all numbers come from the sources below) -
*unconditionally*, one line under the ``# `` heading. But ``_title_from`` copies
the request's subject onto that heading, so a request naming a figure
(「解約率30%の改善レポート」「2024年度の売上」) put an unsourced number on the cover
right beside the blanket promise. ``validate_document`` never caught it (its
number check starts below the first heading), and C-1476 added a disclosure two
sections down in 「まだ埋まっていないこと」 - but the cover kept asserting every
number was sourced, so a headline statistic nothing in the evidence supported
read as SIDRA-verified, and the document contradicted itself: cover says all
sourced, section three says the title figure is unconfirmed.

The fix scopes the cover's promise. When the title carries a number the evidence
does not carry, the preamble says 「本文の数字は下の出典から」 and names the gap
where the reader first meets the figure, instead of 「数字はすべて…」. A clean
title, or a title number the evidence does carry, keeps the original assurance.

The checks build real ``generate_document`` outputs and read the cover line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
#: The unconditional promise the cover must not make beside an unsourced figure.
_BLANKET = "数字はすべて下の出典から"
#: The C-1476 disclosure two sections down; a regression sentinel here.
_SECTION3 = "タイトルに含まれる数値は、索引した根拠では確認できませんでした"


def _preamble(markdown: str) -> str:
    return next(
        (line for line in markdown.splitlines() if line.startswith("> SIDRA AI")),
        "",
    )


@dataclass(frozen=True)
class ReportCoverClaimResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_report_cover_number_claim_matches_its_sourcing() -> ReportCoverClaimResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    stat_facts = [Fact("解約率は改善した。", "docs/churn.md")]
    stat = generate_document("解約率30%の改善レポートを作って", facts=stat_facts, now=_NOW)
    stat_cover = _preamble(stat.markdown)

    # --- (A) an unsourced title number drops the unconditional blanket claim --
    add(_BLANKET not in stat_cover,
        "A: the cover still asserts all numbers are sourced beside an unsourced title number")

    # --- (B) the cover names the unconfirmed title number (discloses up front) -
    add("タイトル" in stat_cover and ("確認できて" in stat_cover or "未確認" in stat_cover),
        "B: the cover does not name the title number as unconfirmed")

    # --- (C) a clean title keeps the original assurance (no false alarm) ------
    clean = generate_document("競合分析のレポートを作って",
                              facts=[Fact("競合Aは値下げした。", "docs/market.md")], now=_NOW)
    add(_BLANKET in _preamble(clean.markdown),
        "C: a number-free title lost its 'all numbers sourced' assurance")

    # --- (D) a title number the evidence carries keeps the blanket claim ------
    #         (weaken the cover only when the figure is genuinely unsourced)
    sourced = generate_document("売上30%増のレポートを作って",
                                facts=[Fact("売上は30%伸びた。", "docs/sales.md")], now=_NOW)
    add(_BLANKET in _preamble(sourced.markdown),
        "D: a title number the evidence carries wrongly weakened the cover claim")

    # --- (E) the section-three disclosure (C-1476) still fires ----------------
    add(_SECTION3 in stat.markdown,
        "E: the section-three unsourced-title disclosure regressed")

    # --- (F) the document still validates as usable --------------------------
    #         (a title number is out of the body validator's scope by design)
    add(validate_document(stat, stat_facts)["usable"],
        "F: an unsourced-title report is no longer usable")

    total = 6
    return ReportCoverClaimResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ReportCoverClaimResult",
    "evaluate_report_cover_number_claim_matches_its_sourcing",
]
