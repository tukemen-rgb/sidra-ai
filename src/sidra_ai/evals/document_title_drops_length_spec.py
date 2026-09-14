"""Does a generated document's title drop a requested length specifier?

C-1822. A request that names how *long* the report should be - 「3ページの
レポートを作って」, 「2000字のレポートを作って」 - is naming a length, not a
subject. ``_title_from`` peeled the kind word (C-1467) and the file-format word
(C-1484) but not the length specifier, so 「3ページ」 rode onto the cover as the
title. Worse than a bad heading: the number then entered the body and the
report's number-check failed 「numbers not present in the evidence: 3」 - a
general user asking for a three-page report got a report titled 「3ページ」 and a
cryptic validation error about the number 3.

The deck side does not turn 「5枚のスライド」 into a cover reading 「5枚」; only the
document had this gap (its length-count twin, the deck honouring the count, is
C-1821). The fix strips a *leading* length specifier - digits followed by a
length unit (ページ/頁/字/文字/枚) and the の or end that closes it - once, before
the tail-anchored peel loop, so 「3ページのレポート」 falls to the default title and
「3ページの競合分析のレポート」 titles 「競合分析」.

It must not touch a subject that merely contains a number: 「第3四半期」,
「3年計画」, 「G3」 are real subjects, and 年/四半期/組/万円 are not length units, so
the gated strip (unit ∈ {ページ,頁,字,文字,枚}, closed by の/$) leaves them whole.

This eval drives the real ``generate_document`` and reads ``document.title``.
"""

from __future__ import annotations

from dataclasses import dataclass

# A leading length specifier: the title must be the subject alone (or the default
# 「レポート」 when the length was the only thing said), never the length the
# request asked the report to run to.
_STRIP = (
    ("3ページのレポートを作って", "レポート"),
    ("10ページのレポートを作って", "レポート"),
    ("2000字のレポートを作って", "レポート"),
    ("3ページの競合分析のレポートを作って", "競合分析"),
    ("5枚の売上のレポートを作って", "売上"),
)

# Must stay correct. A number is part of many real subjects: a quarter, a
# multi-year plan, a product code, and units that are not lengths (組/ヶ月/万円).
# The last is the plain no-length regression guard.
_KEEP = (
    ("第3四半期のレポートを作って", "第3四半期"),
    ("3年計画のレポートを作って", "3年計画"),
    ("G3のレポートを作って", "G3"),
    ("5枚組の写真集のレポートを作って", "5枚組の写真集"),
    ("300万円の予算のレポートを作って", "300万円の予算"),
    ("競合分析のレポートを作って", "競合分析"),
)


@dataclass(frozen=True)
class DocumentLengthTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_title_drops_length_spec() -> DocumentLengthTitleResult:
    from sidra_ai.creation.documents import generate_document

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request, expected in (*_STRIP, *_KEEP):
        title = generate_document(request).title
        add(title == expected,
            f"title {title!r} != {expected!r} for {request!r}")

    total = len(_STRIP) + len(_KEEP)
    return DocumentLengthTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DocumentLengthTitleResult",
    "evaluate_document_title_drops_length_spec",
]
