"""Does a deck disclose a figure in its title that no evidence supports?

C-1799. The report (documents.py, C-1772) already scopes its promise and says so
when the title carries a number the corpus does not support - 「解約率30%の改善」
puts 30% on the cover, and nothing sourced it. The deck never got that fix: its
cover shows the same unsourced 30% while the footer promises 「数字は索引した文書
から引いたものだけを載せ…（推測で埋めません）」 - a blanket "every number is
sourced" claim standing directly under an unsourced one. The deck now scopes the
promise to the body and adds the same caveat as the report; a clean title, or a
title whose number the evidence supports, keeps the original assurance.

The checks drive the real ``generate_deck``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import Fact, generate_deck

_CAVEAT = "タイトルの数値は索引した根拠では確認できていません"
_SCOPED = "本文の数字は"
_BLANKET = "。数字は索引した文書から引いたものだけ"


@dataclass(frozen=True)
class DeckTitleNumberResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_discloses_unsourced_title_number() -> DeckTitleNumberResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    unsourced = generate_deck("解約率30%の改善のスライドを作って").html   # 30% only in the title
    clean = generate_deck("新商品の企画のスライドを作って").html            # no number in the title
    # A title number the evidence supports is a sourced figure, not a caveat.
    sourced = generate_deck(
        "解約率30%の改善のスライドを作って",
        facts=[Fact(text="解約率は30%改善した", source="repo@abc:docs/kpi.md")],
    ).html

    # --- (A) an unsourced title number is disclosed ----------------------
    add(_CAVEAT in unsourced,
        "A: the deck does not disclose that its title number is unsourced")
    # --- (B) the numbers promise is scoped to the body -------------------
    add(_SCOPED in unsourced,
        "B: the deck did not scope its numbers promise to the body")
    # --- (C) the disclosure is additive: the footer still stands ---------
    add(_CAVEAT in unsourced and "推測で埋めません" in unsourced and "<section" in unsourced,
        "C: the disclosure replaced the deck instead of augmenting it")
    # --- (D) a clean title carries no caveat (no false positive) ---------
    add(_CAVEAT not in clean,
        "D: a clean-title deck wrongly claims its title number is unsourced")
    # --- (E) a clean title keeps the original blanket assurance ----------
    add(_BLANKET in clean and _SCOPED not in clean,
        "E: a clean-title deck wrongly scoped its numbers promise")
    # --- (F) a title number the evidence supports is not caveated --------
    add(_CAVEAT not in sourced,
        "F: a sourced title number was wrongly flagged as unconfirmed")

    total = 6
    return DeckTitleNumberResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DeckTitleNumberResult",
    "evaluate_deck_discloses_unsourced_title_number",
]
