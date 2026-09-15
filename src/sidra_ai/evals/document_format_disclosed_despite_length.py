"""Does the report still say it could not make the requested format when a
length spec trails the format word?

C-1845, the word-order re-opening of C-1834. The document generator only writes
Markdown, so when a request names a format it cannot produce (Word/PDF/Excel),
`requested_format` detects it and the job appends 「なお Word 形式では作れないため
Markdown で保存しています」 - the honesty that a reader who wanted Word is not
handed Markdown believing it is Word (C-1834; the deck reuses the same function,
C-1838).

But `requested_format` matched the format word only at the tail of the request
(`_DOC_FORMAT_SUFFIX` is `$`-anchored). The natural phrasing puts a length after
it - 「サイトのレポートをWordで3ページで作って」 - which pushes the format word off
the tail, so the function returns "" and the disclosure never fires: the reader
who asked for Word gets Markdown with no word about it. C-1834's exact hole, on a
word order C-1834 did not cover, the sibling of the C-1843 title bug.

The fix drops the length/size phrase (`drop_size_phrases`, the shared helper the
titles already use, C-1833) before the format search, so the format word reaches
the tail. The strict format gate is unchanged, so a format word that names the
subject - 「Wordの使い方」「PDFで管理する方法」 - and a subject merely ending in
ワード (「パスワード」) still return "".
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.documents import requested_format


#: (request, expected format label). A length spec trails the format word, so the
#: format must still be detected (these are the cases that regressed).
_LENGTH_AFTER_FORMAT: tuple[tuple[str, str], ...] = (
    ("サイトのレポートをWordで3ページで作って", "Word"),
    ("競合分析のレポートを3ページでPDFで作成して", "PDF"),
    ("売上のレポートをExcelで2000字でまとめて", "Excel"),
    ("企画書をワードで5ページでまとめて", "Word"),
)

#: The format word already sits at the tail: unchanged behaviour (C-1834).
_FORMAT_AT_TAIL: tuple[tuple[str, str], ...] = (
    ("サイトのレポートをWordで作って", "Word"),
    ("競合分析をPDFでまとめて", "PDF"),
)

#: No format was requested: the word names the subject, or merely ends a word, or
#: is absent. Must stay "" - the fix strips lengths, not the format gate. The
#: 「キーワードを3つ作って」 case is load-bearing twice over: dropping the count
#: 「3つ」 leaves 「キーワード」 ending in ワード at the very tail, and only the を/の
#: lookbehind (ワード here follows ー, not を/の) keeps it from reading as a Word
#: request - so it guards that the new length strip did not defeat that gate.
_NO_FORMAT: tuple[tuple[str, str], ...] = (
    ("Wordの使い方のレポートを作って", ""),
    ("PDFで管理する方法のレポートを作って", ""),
    ("パスワードのレポートを作って", ""),
    ("キーワードを3つ作って", ""),
    ("売上のレポートを作って", ""),
)


@dataclass(frozen=True)
class FormatDisclosedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_format_disclosed_despite_length() -> FormatDisclosedResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request, expected in _LENGTH_AFTER_FORMAT + _FORMAT_AT_TAIL + _NO_FORMAT:
        got = requested_format(request)
        add(got == expected,
            f"requested_format({request!r}) = {got!r} != {expected!r}")

    total = len(_LENGTH_AFTER_FORMAT) + len(_FORMAT_AT_TAIL) + len(_NO_FORMAT)
    return FormatDisclosedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "FormatDisclosedResult",
    "evaluate_document_format_disclosed_despite_length",
]
