"""Does a deck disclose that a requested structure was substituted?

C-1793. The deck builds one of two fixed outlines - pitch or 進捗報告 -
``choose_outline`` picking status for a handful of words and defaulting
everything else to pitch. A request that names a structure the deck cannot
build (「SWOT分析のスライド」「タイムラインのスライド」) is answered with the
pitch template under the asked-for title, and neither the deck HTML (the
artifact that is forwarded and reopened) nor the chat summary said the
structure was not the one requested. ``outline_fallback_note`` is now the
shared source of that admission for both, the same way ``genre_fallback_note``
(C-1788) is shared by the game page and its summary. A bare request, or a
structure the deck does build, adds no note.

The checks drive the real ``generate_deck`` and ``build_deck_generator``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "代わりに標準の"


@dataclass(frozen=True)
class DeckOutlineFallbackResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    gen = build_deck_generator(scratch_dir())
    outcome = gen(request, detect_creation_intent(request))
    return getattr(outcome, "summary", "") or ""


def evaluate_deck_discloses_outline_fallback() -> DeckOutlineFallbackResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    swot = generate_deck("SWOT分析のスライドを作って").html
    timeline = generate_deck("タイムラインのスライドで作って").html
    bare = generate_deck("スライドを作って").html
    weekly = generate_deck("週報のスライドを作って").html      # a shape we build (status)

    # --- (A) a recognised-unbuildable structure is disclosed on the deck --
    add(_NOTE in swot,
        "A: the deck does not disclose the structure substitution for 「SWOT」")
    # --- (B) another one is disclosed too --------------------------------
    add(_NOTE in timeline,
        "B: the deck does not disclose the substitution for 「タイムライン」")
    # --- (C) a bare request carries no note (no false positive) ----------
    add(_NOTE not in bare,
        "C: a bare 「スライドを作って」 wrongly claims a substitution")
    # --- (D) the chat summary discloses it too (shared source) -----------
    add(_NOTE in _summary("SWOT分析のスライドを作って"),
        "D: the chat summary lost the structure substitution disclosure")
    # --- (E) the note is additive: the fill-policy footer still stands ----
    add(_NOTE in swot and "推測で埋めません" in swot,
        "E: the disclosure replaced the deck's own footer instead of adding to it")
    # --- (F) a structure the deck does build (週報→status) adds no note ---
    add(_NOTE not in weekly and _NOTE not in _summary("週報のスライドを作って"),
        "F: a buildable structure (週報) wrongly claims a substitution")

    total = 6
    return DeckOutlineFallbackResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DeckOutlineFallbackResult",
    "evaluate_deck_discloses_outline_fallback",
]
