"""Does the deck keep a negated fact off the capability slide?

C-1461: deck section cues are matched as substrings, so 「対応」 matched inside
「未対応」 and 「未対応の不具合が 3 件残っている」 was placed under いま出来ること (what
we can do now) - a problem shown as a capability - and 残っていること was then
reported as having no evidence. Meanwhile 「決済連携の実装は完了した」 matched no cue
(完了/実装 were absent) and was dropped, leaving いま出来ること falsely empty.

A cue preceded by a negation (未/非/不) no longer counts for the positive
section it stands for, and 完了/実装/リリース/済 were added so completed work lands
on いま出来ること. Negated facts reach 残っていること through their own 残/未 cue.

The checks read ``_matches`` for routing and a real ``generate_deck`` for the
end-to-end slide contents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _slides(html: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sec in re.findall(r"<section class='slide'>.*?</section>", html, re.S):
        head = re.search(r"<h2[^>]*>(.*?)</h2>", sec)
        if not head:
            continue
        lis = [re.sub(r"<[^>]+>", "", x).strip()
               for x in re.findall(r"<li[^>]*>(.*?)</li>", sec, re.S)]
        out[head.group(1)] = lis
    return out


@dataclass(frozen=True)
class DeckNegatedCueResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_negated_cue_not_capability() -> DeckNegatedCueResult:
    from sidra_ai.creation.decks import _matches, generate_deck
    from sidra_ai.creation.evidence import Fact

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def fact(text: str) -> "Fact":
        return Fact(text=text, source="r:x")

    # A negated capability must not land on the positive section its cue stands
    # for (「対応」/「実装」/「解決」 negated by 未).
    add(not _matches("いま出来ること", fact("未対応の不具合が残っている。")),
        "「未対応」 still matched いま出来ること")
    add(not _matches("いま出来ること", fact("通知機能が未実装のまま残っている。")),
        "「未実装」 still matched いま出来ること")
    add(not _matches("解決", fact("課題は未解決である。")),
        "「未解決」 still matched 解決")

    # Genuine completed work belongs on いま出来ること.
    add(_matches("いま出来ること", fact("決済連携の実装は完了した。")),
        "completed work (実装/完了) did not match いま出来ること")
    add(_matches("いま出来ること", fact("検索機能に対応した。")),
        "a genuine 対応 (not negated) did not match いま出来ること")
    add(_matches("いま出来ること", fact("新機能をリリース済み。")),
        "リリース済み did not match いま出来ること")

    # End to end: a completed fact fills いま出来ること (not a placeholder), and a
    # non-numeric remaining fact fills 残っていること and is kept off いま出来ること.
    facts = [
        fact("決済連携の実装は完了した。"),
        fact("通知機能が未実装のまま残っている。"),
    ]
    slides = _slides(generate_deck("週次進捗のスライドを作って", facts=facts).html)
    now = slides.get("いま出来ること", [])
    remaining = slides.get("残っていること", [])
    add(any("完了" in b for b in now) and not any("〔" in b for b in now),
        f"いま出来ること was not filled by the completed fact: {now}")
    add(any("未実装" in b for b in remaining)
        and not any("未実装" in b for b in now),
        f"the remaining fact was misplaced: now={now}, remaining={remaining}")

    total = 8
    return DeckNegatedCueResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckNegatedCueResult", "evaluate_deck_negated_cue_not_capability"]
