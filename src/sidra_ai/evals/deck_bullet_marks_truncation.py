"""Does a deck bullet say when the 120-char cap truncated a long fact?

C-1851, the deck-bullet member of the truncation-honesty family (C-1264 for the
citation excerpt, C-1217/C-1849 for numbers, C-1680 for "say when it is not the
whole thing"). A deck bullet is capped at 120 characters and then run through
``whole_sentences``, which trims a multi-sentence slice back to a clean sentence
end. But a *single long clause* - a fact with no 。 in its first 120 characters -
has nothing to trim to, so ``whole_sentences`` returns the raw 120-char cut whole
(its own docstring: "a terminator-free fragment passes whole"). The bullet then
ends mid-clause, and for a figure straddling the cap mid-digit - 「…2024年度には
1,23」 - with no 「…」 at all: it reads as the whole fact when it is a fragment, and
shows a partial number as a small whole value. The C-1217 comment in ``decks.py``
names exactly this ("a bullet cut there reads … (C-1217)") as the case it did not
cover.

A bullet the cap truncated into a mid-clause fragment now ends with 「…」, and a
partial number at the cut is dropped first (C-1849), so the reader sees it was
clipped. A bullet ``whole_sentences`` could trim to a real sentence end is
untouched, and a fact that fits under the cap keeps its exact text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.evidence import Fact

#: Digits and in-number separators: a marked bullet must not end (before 「…」) on
#: one, or a partial figure is shown as whole.
_NUMBER_CHARS = frozenset("0123456789０１２３４５６７８９,，.．")

_LONG = "ユーザー定着率の継続的な改善であり"  # 16 chars, no 。


def _bullet(fact_text: str) -> str:
    """The 課題-slide bullet a deck builds from one fact (「主要課題は…」 lands there)."""
    deck = generate_deck("GAMEYARD のスライドを作って", facts=[Fact(fact_text, "owner/repo docs/x.md")])
    for raw in re.findall(r"<li>(.*?)</li>", deck.html, re.S):
        text = re.sub(r"<[^>]+>", "", raw)
        if "主要課題" in text:
            return text
    return ""


@dataclass(frozen=True)
class DeckBulletResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_bullet_marks_truncation() -> DeckBulletResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A single long clause with no sentence end in the cap: the bullet is a
    # fragment and must say so.
    long_plain = _bullet("主要課題は" + _LONG * 8)
    add(long_plain.endswith("…"), f"truncated long clause carries no 「…」: {long_plain[-12:]!r}")
    add("主要課題" in long_plain, "the bullet lost its real content")

    # ...and a figure straddling the cap must not be shown mid-digit.
    long_number = _bullet("主要課題は" + _LONG * 6 + "2024年度には 1,234,567,890 円規模")
    add(long_number.endswith("…"), f"truncated numeric clause carries no 「…」: {long_number[-12:]!r}")
    add(len(long_number) >= 2 and long_number[-2] not in _NUMBER_CHARS,
        f"figure cut mid-digit in a bullet: {long_number[-12:]!r}")

    long_fullwidth = _bullet("主要課題は" + _LONG * 6 + "総額は１２３４５６７８９０１２３４円")
    add(len(long_fullwidth) >= 2 and long_fullwidth[-2] not in _NUMBER_CHARS,
        f"fullwidth figure cut mid-digit in a bullet: {long_fullwidth[-12:]!r}")

    # A *whole* figure before the cut is kept, not over-trimmed (the cut is in the
    # prose that follows it, not in the number itself).
    whole_figure = _bullet("主要課題は" + _LONG * 6 + "総額は42円と発表されたが詳細は今も不明のまま")
    add("42" in whole_figure, f"a whole figure before the cut was trimmed away: {whole_figure[-12:]!r}")

    # A slice with a sentence end within the cap trims to it - no spurious mark.
    clean = _bullet("主要課題は定着率である。" + "詳細は別途に記載する。" * 15)
    add(clean.endswith("。") and not clean.endswith("…"),
        f"a whole-sentence bullet was wrongly marked: {clean[-12:]!r}")
    add("主要課題は定着率である。" in clean, "the whole-sentence bullet lost content")

    # A fact under the cap keeps its exact text, no mark.
    short = _bullet("主要課題は定着率である。")
    add(short == "主要課題は定着率である。", f"a short fact was altered: {short!r}")
    add("…" not in short, "a short fact was marked as truncated")

    # The mark is only for a real truncation: a long clause that is nonetheless
    # whole (fits the cap exactly) is not marked. 「主要課題は」+ 「あ」*110 = 115 < 120.
    fits = _bullet("主要課題は" + "あ" * 110)
    add("…" not in fits, f"a fact within the cap was marked: {fits[-6:]!r}")
    add(fits.endswith("あ"), f"a within-cap fact was altered: {fits[-6:]!r}")

    total = 12
    return DeckBulletResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckBulletResult", "evaluate_deck_bullet_marks_truncation"]
