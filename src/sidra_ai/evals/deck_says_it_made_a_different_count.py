"""Does a deck say it is not the number of slides that was asked for?

C-1821. Both outlines are fixed at four sections and there is no size to set,
so 「5枚のスライドを作って」 built four slides and neither the deck HTML (the
artifact that is forwarded and reopened) nor the chat summary mentioned the
number - the request's 5 was read by nobody. ``slide_count_note`` is now the
single source of that admission for both, the same way ``outline_fallback_note``
(C-1793) is shared one generator over.

The silence has to stay silent where there is nothing to report: a request
that named no size, and a request whose size happens to match what was built,
add no note. A number that is not a size (「5年計画」) is not a request either.

The checks drive the real ``generate_deck`` and ``build_deck_generator``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import generate_deck, slide_count_note
from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir

#: The sentence's stable half - the part that says the size cannot be chosen.
_NOTE = "枚数は指定できません"

#: C-1793's note, checked here only to prove the two coexist.
_STRUCTURE = "代わりに標準の"


@dataclass(frozen=True)
class DeckSlideCountResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    gen = build_deck_generator(scratch_dir())
    outcome = gen(request, detect_creation_intent(request))
    return getattr(outcome, "summary", "") or ""


def evaluate_deck_says_it_made_a_different_count() -> DeckSlideCountResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    asked_five = generate_deck("5枚のスライドを作って")
    bare = generate_deck("スライドを作って").html
    asked_four = generate_deck("4枚のスライドを作って").html
    asked_pages = generate_deck("10ページのスライドを作って").html
    both = generate_deck("SWOT分析を5枚のスライドで作って").html
    five_year = generate_deck("5年計画のスライドを作って").html
    percent = generate_deck("売上5%のスライドを作って").html
    hundred = generate_deck("100枚のスライドを作って").html

    # --- (A) the deck itself says the size is not the one asked for -------
    add(_NOTE in asked_five.html,
        "A: the deck does not disclose that it is not 5 slides")
    # --- (B) and so does the chat summary, from the same source -----------
    add(_NOTE in _summary("5枚のスライドを作って"),
        "B: the chat summary lost the slide-count disclosure")
    # --- (C) a request that named no size gets no note --------------------
    add(_NOTE not in bare and _NOTE not in _summary("スライドを作って"),
        "C: a bare 「スライドを作って」 wrongly reports a size it was never asked for")
    # --- (D) a size that happens to match is not a substitution -----------
    add(_NOTE not in asked_four and _NOTE not in _summary("4枚のスライドを作って"),
        "D: 「4枚」 - the size actually built - wrongly gets a mismatch note")
    # --- (E) the same request said in pages is still a size ---------------
    add(_NOTE in asked_pages,
        "E: 「10ページ」 was not read as a size")
    # --- (F) additive: C-1793's structure note and the deck footer stand --
    add(_NOTE in both and _STRUCTURE in both and "推測で埋めません" in both,
        "F: the count note replaced the structure note or the deck's own footer")
    # --- (G) a number that is not a size is not a request ------------------
    #     The unit word carries this, not a word list: 「5年」「5%」 have no digits
    #     in front of 枚/ページ/スライド, so they never match.
    add(_NOTE not in five_year and _NOTE not in percent,
        "G: a year span or a percentage was read as a request for five slides")
    # --- (I) a size bigger than two digits is still a size -----------------
    #     「100枚のスライドを作って」 is the request this note exists for, and the
    #     first bound on the pattern let exactly that one through silent.
    add(_NOTE in hundred,
        "I: 「100枚」 was not read as a size")
    # --- (H) the note reports the count it was given, not a constant -------
    made_seven = slide_count_note("5枚のスライドを作って", 7)
    add("7 枚" in made_seven and "5 枚" in made_seven,
        "H: the note does not name the size actually built")

    return DeckSlideCountResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see the rule in sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "DeckSlideCountResult",
    "evaluate_deck_says_it_made_a_different_count",
]
