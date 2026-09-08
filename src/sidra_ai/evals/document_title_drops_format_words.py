"""Does a generated document's title drop a requested file-format word?

C-1484, the document twin of the deck C-1465. A request that names the file
format it wants - 「売上のレポートを Word で作って」, 「競合分析を PDF でまとめて」 -
left the format word on the cover: the title came out 「売上のレポートを Word」,
「競合分析を PDF」. ``_title_from`` peels a trailing kind word (C-1467), but the
kind list is tail-anchored, and a trailing 「…を Word で」 pushes the kind word off
the tail so nothing strips, and the format word itself is not a kind word, so it
rides into the title - the heading, the 概要 and the confirmation all corrupted.

The deck already handles the analogue (「提案をパワポで作って」→「提案」) by listing
パワポ/pptx/powerpoint among its kind words. The document could not do the same
naïvely: a tail-anchored, case-insensitive 「word」 would over-strip キーワード /
keyword / パスワード / password. The fix strips a format word only when it sits
right after を or の (`(?<=[をの])`) - which is where the instrumental phrase puts
it, and which キーワード / パスワード never satisfy (their ワード follows ス / ー),
so real subjects survive and a bare leading format word (「Word で報告書」, which
has no subject to corrupt) is left untouched rather than peeled to nothing.

This eval drives the real ``generate_document`` and reads ``document.title``.
"""

from __future__ import annotations

from dataclasses import dataclass

# A named format at the tail of a subject-bearing request: the title must be the
# subject alone, never the file format the request asked to render it in.
_STRIP = (
    ("売上のレポートをWordで作って", "売上"),
    ("競合分析をPDFでまとめて", "競合分析"),
    ("月次のレポートをdocxで作って", "月次"),
    ("予算表をエクセルで作って", "予算表"),
    ("計画の報告書をPDFで作って", "計画"),
)

# Must stay correct. The first two are the reason the strip is lookbehind-gated,
# not tail-anchored alone: their subject *ends in* ワード, but the ー before it is
# not を/の, so a bare 「ワード$」 would wrongly peel キー / パス while the gated
# strip leaves them whole. The rest cover a format word that is itself the subject
# (mid-phrase, or followed by の) and a plain no-format regression guard.
_KEEP = (
    ("キーワードのレポートを作って", "キーワード"),
    ("パスワードの資料を作って", "パスワード"),
    ("Wordの使い方のレポートを作って", "Wordの使い方"),
    ("エクセル関数の解説をまとめて", "エクセル関数の解説"),
    ("競合分析のレポートを作って", "競合分析"),
)


@dataclass(frozen=True)
class DocumentFormatTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_title_drops_format_words() -> DocumentFormatTitleResult:
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
    return DocumentFormatTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DocumentFormatTitleResult",
    "evaluate_document_title_drops_format_words",
]
