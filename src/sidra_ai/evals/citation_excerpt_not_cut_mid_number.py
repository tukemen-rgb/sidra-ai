"""Does a clipped citation excerpt avoid ending inside a number?

C-1849, the citation-excerpt sibling of C-1217. The /v1/chat citation excerpt is
capped at ``MAX_CITATION_EXCERPT_CHARS`` and marks a clipped tail with 「…」 so the
operator knows they are looking at a slice (C-1264). But the tail was cut at
exactly the budget, mid-character, and for a number that means mid-digit: a chunk
whose figure straddles the boundary showed 「1,234,567,890 円」 as 「…1,2…」. The 「…」
says it was clipped, but 「1,2」 reads as a small complete value - the very
misreading a cited figure exists to prevent, and the one the report body already
refuses (C-1217: an ASCII dot inside 「3.5」 is spelling, not a sentence end).

The excerpt now drops a partial number back to its start when the budget splits
one (the next dropped character is a digit); the 「…」 still says it was clipped. A
number that simply *ends* at the budget - the next character is not another digit
- is whole and kept, so no figure is lost.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.api.citations import citation_excerpt
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS as _M
from sidra_ai.security.output_guard import OutputGuard

_GUARD = OutputGuard()

#: Digits and in-number separators. A clipped excerpt must not end (before its
#: 「…」) on any of these, or a partial figure is being shown as whole.
_NUMBER_CHARS = frozenset("0123456789０１２３４５６７８９,，.．")


def _ends_mid_number(excerpt: str) -> bool:
    return excerpt.endswith("…") and len(excerpt) >= 2 and excerpt[-2] in _NUMBER_CHARS


def _excerpt(content: str) -> str:
    return citation_excerpt(content, _GUARD, query="売上")[0]


# The query term 「売上」 sits at the head so the window opens at 0; the filler
# pushes a figure onto the budget boundary so the tail cut lands inside it.
_HEAD = "売上について。"
_PAD = "あ" * (_M - len(_HEAD) - 4)

#: A figure straddles the budget: the tail cut falls between its digits.
_STRADDLE_GROUPED = _HEAD + _PAD + "1,234,567,890 円で着地。"
_STRADDLE_FULLWIDTH = _HEAD + _PAD + "１２３４５６７８ 円で着地。"
_STRADDLE_DECIMAL = _HEAD + _PAD + "3.14159265 で着地。"
_STRADDLE_PLAIN = _HEAD + _PAD + "987654321 で着地。"

#: A figure ends at (or before) the budget and prose follows: the number is whole
#: and must be kept - the cut is in the prose, not the number.
_WHOLE_AT_EDGE = "売上について。" + "あ" * (_M - len("売上について。") - 6) + "9,800円 ん" * 5
_WHOLE_THEN_PROSE = "売上について。" + "あ" * (_M - len("売上について。") - 5) + "42 という数字。" + "ん" * 20
_NUMBER_IN_PROSE = "売上について。2024年度の売上は 9,800 万円。" + "ん" * _M

#: Short enough that nothing is cut: no 「…」, the figure is shown in full.
_NO_CUT = "売上は 1,234,567 円。"


@dataclass(frozen=True)
class ExcerptNumberResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_citation_excerpt_not_cut_mid_number() -> ExcerptNumberResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    grouped = _excerpt(_STRADDLE_GROUPED)
    add(not _ends_mid_number(grouped), f"grouped figure cut mid-digit: {grouped[-12:]!r}")
    add(grouped.endswith("…"), "clipped excerpt lost its 「…」 slice mark")
    add("売上" in grouped, "the excerpt was trimmed past its real content")

    fullwidth = _excerpt(_STRADDLE_FULLWIDTH)
    add(not _ends_mid_number(fullwidth), f"fullwidth figure cut mid-digit: {fullwidth[-12:]!r}")

    decimal = _excerpt(_STRADDLE_DECIMAL)
    add(not _ends_mid_number(decimal), f"decimal figure cut mid-digit: {decimal[-12:]!r}")

    plain = _excerpt(_STRADDLE_PLAIN)
    add(not _ends_mid_number(plain), f"plain integer cut mid-digit: {plain[-12:]!r}")

    # A whole number at the boundary must not be trimmed away (no over-trim).
    add("9,800" in _excerpt(_WHOLE_AT_EDGE),
        "a whole figure at the budget edge was trimmed as if partial")
    add("42" in _excerpt(_WHOLE_THEN_PROSE),
        "a whole figure followed by prose was trimmed")
    add("9,800" in _excerpt(_NUMBER_IN_PROSE),
        "a figure well inside the window was lost")

    no_cut = _excerpt(_NO_CUT)
    add("…" not in no_cut and "1,234,567" in no_cut,
        "an un-clipped excerpt was marked or altered")

    total = 10
    return ExcerptNumberResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ExcerptNumberResult", "evaluate_citation_excerpt_not_cut_mid_number"]
