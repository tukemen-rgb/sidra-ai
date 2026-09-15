"""Does the answer body avoid ending inside a number at its 400-char cap?

C-1852, the answer-body member of the truncation-honesty family (C-1849 for the
citation excerpt, C-1851 for the deck bullet, C-1217 for the report body). The
echo answer opens each cited block with a query-relevant lead capped at 400
characters and marked with 「...」 when it overflows. But the cap cut at exactly
400, mid-character, and for a number that means mid-digit: a long single-clause
answer whose figure straddles the cap showed 「…であり 1,23...」 - a partial number
that reads as a small whole value, the misreading a shown figure exists to
prevent and every sibling surface already refuses.

The lead now drops a partial number back to its start when the cap splits one
(the character after the cut is a digit); the 「...」 still marks the overflow. A
number that merely ends at the cap - the next character is not another digit - is
whole and kept.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.models.echo import EchoModelAdapter

_MODEL = EchoModelAdapter()

#: Digits and in-number separators; the char before the 「...」 mark must not be one.
_NUMBER_CHARS = frozenset("0123456789０１２３４５６７８９,，.．")

_PAD = "あ" * 396  # pushes the figure onto the 400-char cap boundary


def _lead(content: str) -> str:
    return _MODEL._lead(content, "売上")


def _ends_mid_number(lead: str) -> bool:
    # 「...」 is a three-dot mark; the character before it must not be a number char.
    return lead.endswith("...") and len(lead) >= 4 and lead[-4] in _NUMBER_CHARS


def _straddle(number: str) -> str:
    return "売上" + _PAD + number + "円" + "あ" * 20


@dataclass(frozen=True)
class AnswerLeadNumberResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_answer_lead_not_cut_mid_number() -> AnswerLeadNumberResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    grouped = _lead(_straddle("1,234,567,890"))
    add(not _ends_mid_number(grouped), f"grouped figure cut mid-digit: {grouped[-10:]!r}")
    add(grouped.endswith("..."), "clipped lead lost its 「...」 mark")
    add("売上" in grouped, "the lead was trimmed past its real content")

    fullwidth = _lead(_straddle("１２３４５６７８９０１２"))
    add(not _ends_mid_number(fullwidth), f"fullwidth figure cut mid-digit: {fullwidth[-10:]!r}")

    decimal = _lead(_straddle("3.14159265358979"))
    add(not _ends_mid_number(decimal), f"decimal figure cut mid-digit: {decimal[-10:]!r}")

    # A whole figure the cut merely follows is kept (no over-trim).
    guard = _lead("売上" + "あ" * 390 + "は42と" + "ん" * 16)
    add("42" in guard, f"a whole figure before the cut was trimmed: {guard[-12:]!r}")
    add(guard.endswith("..."), "the over-trim-guard lead lost its 「...」 mark")
    add(not _ends_mid_number(guard), f"the over-trim-guard lead ends mid-number: {guard[-10:]!r}")

    # A lead within the cap is untouched: no mark, figure intact.
    short = _lead("売上は 1,234,567 円。")
    add("..." not in short, "an un-clipped lead was marked")
    add("1,234,567" in short, "an un-clipped lead lost its figure")

    total = 10
    return AnswerLeadNumberResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["AnswerLeadNumberResult", "evaluate_answer_lead_not_cut_mid_number"]
