"""Does an empty report's cover still promise its numbers are sourced?

C-1803. ``generate_document`` stamps one line under the title, and for every
case but one - a title carrying an unsourced number, handled by C-1772 - that
line reads 「数字はすべて下の出典から」. When the index returns nothing
(``not retrieved``) and the title has no number, the body is entirely
〔社長が埋める欄〕 placeholders, the 「出典」 section says 「根拠は見つかりません
でした」, and 「まだ埋まっていないこと」 discloses the miss - yet the cover still
made the blanket promise. Reopened or forwarded on its own, the first and most
authoritative line read as a normally-sourced report; the chat reply was honest
(「中身のある資料を作れませんでした。索引にこの依頼の根拠がありません」) but the saved
file's cover was not.

The fix adds a third preamble branch, between C-1772's and the blanket, for the
empty case: it states the truth the module already computed - no evidence, an
empty draft, no numbers - and makes no sourcing promise. The C-1772 branch (a
title number the evidence does not carry) is untouched, so an empty draft whose
*title* has a number still discloses that gap; the blanket promise stays for
genuinely sourced documents.

The checks build real ``generate_document`` outputs and read the cover line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)
_BLANKET = "数字はすべて下の出典から"
_ANY_SOURCE_PROMISE = "下の出典から"
_EMPTY_DISCLOSURE = "索引にこの依頼の根拠が無く"
_TITLE_NUMBER_DISCLOSURE = "タイトルの数値は索引した根拠では確認できていません"


@dataclass(frozen=True)
class DocCoverEmptyResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _cover(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith(">"):
            return line
    return ""


def evaluate_document_cover_honest_when_empty() -> DocCoverEmptyResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # An empty draft (no evidence, no title number) is the defect case.
    empty = generate_document("所有権についてレポートを書いて", facts=[], now=_NOW)
    empty_cover = _cover(empty.markdown)
    # A: the blanket sourcing promise is gone from the empty cover.
    add(_BLANKET not in empty_cover, "empty cover still makes the blanket promise")
    # B: the cover discloses the empty, no-evidence state.
    add(_EMPTY_DISCLOSURE in empty_cover, "empty cover does not disclose the miss")
    # C: no sourcing promise of any wording survives on an empty cover.
    add(
        _ANY_SOURCE_PROMISE not in empty_cover,
        "empty cover still promises numbers come from sources",
    )

    # A genuinely sourced document keeps its promise - the fix is scoped.
    sourced = generate_document(
        "進捗レポートを書いて", facts=[Fact("完了は 42 件。", "docs/s.md")], now=_NOW
    )
    # D: the sourced cover is untouched.
    add(_BLANKET in _cover(sourced.markdown), "sourced cover lost its promise")

    # An empty draft whose TITLE carries a number still uses C-1772's branch.
    empty_numbered = generate_document(
        "2025年度の計画レポートを書いて", facts=[], now=_NOW
    )
    # E: C-1772 is preserved - the title-number gap is still disclosed.
    add(
        _TITLE_NUMBER_DISCLOSURE in _cover(empty_numbered.markdown),
        "empty+numbered cover no longer discloses the title-number gap (C-1772)",
    )

    # F: the empty draft is still a usable skeleton - the cover fix did not
    # touch validation.
    add(validate_document(empty, [])["usable"], "empty draft no longer usable")

    total = 6
    return DocCoverEmptyResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DocCoverEmptyResult", "evaluate_document_cover_honest_when_empty"]
