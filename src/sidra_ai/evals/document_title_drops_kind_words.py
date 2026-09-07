"""Does a generated document's title drop the deliverable-kind word it is?

C-1467, the document twin of the deck C-1465, plus the follow-through C-1458
missed. A report titled 「競合分析のレポート」 prints 「レポート」 in its own ``#``
heading beside a file that is a report (C-1246), so ``_title_from`` drops a
trailing kind word. But it did so once, and:

* the deliverable words C-1458 added to the *intent* vocabulary so 「報告書」
  「議事録」「マニュアル」「提案書」「仕様書」「要件定義書」「手順書」「説明書」
  route to DOCUMENT and generate were never added to the *title* kind list, so
  every one of them stayed on the cover (「会議の議事録」 names its own kind);
* stacking a kind word behind a particle or an 「について/に関する」 phrase -
  「競合分析のレポートをドキュメントで作って」, 「広告方針に関する報告書を作って」 -
  dropped only the outer word and left the inner kind word on the cover.

The fix registers the eight deliverable words and peels the trailing particle,
kind word and about-phrase repeatedly until the tail is a real subject. This
eval drives the real ``generate_document`` and reads ``document.title``.
"""

from __future__ import annotations

from dataclasses import dataclass

# The C-1458 deliverable words, and stacked kind/about phrasings: the title must
# be the subject alone, never the deliverable's own kind.
_STRIP = (
    ("会議の議事録を作って", "会議"),
    ("新機能の報告書を作って", "新機能"),
    ("操作マニュアルを作って", "操作"),
    ("新機能の提案書を作って", "新機能"),
    ("システムの要件定義書を作って", "システム"),
    ("競合分析のレポートをドキュメントで作って", "競合分析"),
    ("新機能の報告書を資料でまとめて", "新機能"),
    ("広告方針に関する報告書を作って", "広告方針"),
    ("会議のまとめをドキュメントで作って", "会議"),
)

# Already correct - must stay correct (no over-stripping, no regressions).
_KEEP = (
    ("競合分析のレポートを作って", "競合分析"),
    ("セキュリティ方針についてのレポートを作って", "セキュリティ方針"),
    ("報告書フォーマットの提案書を作って", "報告書フォーマット"),
    ("議事録を作って", "議事録"),
    ("レポートを作って", "レポート"),
)


@dataclass(frozen=True)
class DocumentTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_title_drops_kind_words() -> DocumentTitleResult:
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
    return DocumentTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DocumentTitleResult", "evaluate_document_title_drops_kind_words"]
