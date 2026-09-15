"""Does a report keep a page-count out of its title - from either side?

C-1843, the suffix half of C-1822. A request names how long the report should
run, and that length is not the subject: 「3ページのレポートを作って」 titles
「レポート」, not 「3ページ」 (C-1822). But C-1822 stripped the length only when
it *led* the request. The more natural phrasing puts it behind the subject -
「サイトについてのドキュメントを3ページで作って」 - and there the tail-anchored
kind/format/about peels never reach it, so 「3ページ」 rode onto the cover as part
of the title.

That is not just an ugly title. `_title_from` copies the title's subject into the
body (the 概要, and the 「主題が見つからなかった」 disclosure line when the subject
is not in the index), so the digit 「3」 - a page count, backed by no evidence -
then trips `validate_document`'s fabricated-number check
(「numbers not present in the evidence: 3」). A reader who asked for a 3-page
report is told their report 「検証に落ちています」 (failed verification) over the
page count they themselves requested. The exact failure C-1822 was built to
prevent, on the phrasing C-1822 did not cover.

The fix strips a trailing length (を/の + digits + a length unit) the same way
C-1822 strips a leading one, gated to a real length unit so a subject number
survives: 第3四半期 (四半期 is no unit), 5枚組の写真集 (枚 is not at the tail),
3年計画 (年). A genuine headline statistic - 「解約率30%の改善レポート」 - is not a
length, so it is left in the title and still fails validation, exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.documents import generate_document, validate_document


def _title(request: str) -> str:
    return generate_document(request, facts=[]).title


def _usable(request: str) -> bool:
    # The subject-unmatched path is the one the reader actually hit: it copies
    # the title (page count and all) into the body disclosure line, where the
    # number check can see it.
    document = generate_document(request, facts=[], subject_unmatched=True)
    return bool(validate_document(document, [])["usable"])


#: (request, expected title). The length sits behind the subject and must not
#: reach the cover; the kind word and about-phrase peel as usual.
_TITLE_SUFFIX: tuple[tuple[str, str], ...] = (
    ("サイトについてのドキュメントを3ページで作って", "サイト"),
    ("競合分析のレポートを5ページで作成して", "競合分析"),
    ("売上のレポートを2000字で書いて", "売上"),
)

#: A leading length still falls away (C-1822 unchanged).
_TITLE_PREFIX: tuple[tuple[str, str], ...] = (
    ("3ページのレポートを作って", "レポート"),
    ("3ページの競合分析のレポートを作って", "競合分析"),
)

#: A number that names part of the subject, not a length, survives: the unit is
#: not a length unit (四半期), or the length unit is not at the tail (5枚組).
_TITLE_SUBJECT_NUMBER: tuple[tuple[str, str], ...] = (
    ("第3四半期のレポートを作って", "第3四半期"),
    ("5枚組の写真集のレポートを作って", "5枚組の写真集"),
)


@dataclass(frozen=True)
class DocumentLengthResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_length_suffix_not_a_number() -> DocumentLengthResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request, expected in _TITLE_SUFFIX + _TITLE_PREFIX + _TITLE_SUBJECT_NUMBER:
        got = _title(request)
        add(got == expected, f"title({request!r}) = {got!r} != {expected!r}")

    # The reader's symptom: a requested page count must not fail verification.
    for request, _ in _TITLE_SUFFIX[:2]:
        add(_usable(request),
            f"validate({request!r}) failed over the requested page count")

    # ...but a real headline statistic the evidence does not support must still
    # fail - the fix strips lengths, not numbers (C-1772 preserved).
    add(not _usable("解約率30%の改善レポートを作って"),
        "a fabricated headline statistic (30%) no longer fails validation")

    total = len(_TITLE_SUFFIX) + len(_TITLE_PREFIX) + len(_TITLE_SUBJECT_NUMBER) + 3
    return DocumentLengthResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DocumentLengthResult",
    "evaluate_document_length_suffix_not_a_number",
]
