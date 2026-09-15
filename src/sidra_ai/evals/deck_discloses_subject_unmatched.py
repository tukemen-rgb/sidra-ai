"""Does the deck admit when none of its evidence is about the subject?

C-1846, the deck twin of C-1532. A deck fills each slide from the facts whose
text matches that slide's section cue - so a fact 「主要課題はユーザー定着率」 lands
on the 課題 slide of a 「量子コンピュータ」 deck, and the slide then reads as if
quantum computing's main challenge is user retention. The report caught exactly
this (C-1532): when the request names a subject and no retrieved fact carries it,
the 概要 says 「載っている N 件は…主題に触れていません」 so a forwarded document does
not read as sourced. The deck said nothing - its C-1532 docstring assumed the
deck 「left the slides honestly blank」, but a fact matching a section cue is
placed, not blanked, so a forwarded deck read as backed by its subject.

The deck now carries the same admission, computed the same way
(`subject_unmatched`, evidence.py), only when facts were actually placed (an
empty deck is honestly blank and needs no caveat). The facts are still shown -
they are not dropped (C-1403); it is the sentence beside them that was missing.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.evidence import Fact

#: The distinctive phrase the subject-mismatch caveat carries.
_CAVEAT = "主題との重なりは確認できていません"

_RETENTION = Fact("主要課題はユーザー定着率である", "owner/repo docs/x.md")
_SALES = Fact("売上は前年比で好調である", "owner/repo docs/f.md")


def _html(request: str, facts: list[Fact]) -> str:
    return generate_deck(request, facts=facts).html


@dataclass(frozen=True)
class DeckSubjectResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_discloses_subject_unmatched() -> DeckSubjectResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # Subject named, no placed fact mentions it: the caveat must appear.
    quantum = _html("量子コンピュータのスライドを作って", [_RETENTION])
    add(_CAVEAT in quantum, "量子コンピュータ deck over 定着率 fact carries no subject caveat")
    blockchain = _html("ブロックチェーンのスライドを作って", [_RETENTION])
    add(_CAVEAT in blockchain, "ブロックチェーン deck over 定着率 fact carries no subject caveat")
    # The caveat tells the reader not to read the deck as evidence about the subject.
    add("主題についての根拠として読まないでください" in quantum,
        "the subject caveat does not tell the reader not to treat it as evidence")
    # The mismatched fact is still shown, not dropped (C-1403).
    add("定着率" in quantum, "the deck dropped the off-subject fact instead of disclosing it")
    # The title is still the subject.
    add("<title>量子コンピュータ</title>" in quantum or "<h1>量子コンピュータ</h1>" in quantum,
        "the deck title is not the requested subject")

    # Subject named and a placed fact mentions it: no false caveat.
    retention = _html("定着率のスライドを作って", [_RETENTION])
    add(_CAVEAT not in retention, "定着率 deck over 定着率 fact raised a false subject caveat")
    add("定着率" in retention, "the matching fact vanished from the deck")
    sales = _html("売上のスライドを作って", [_SALES])
    add(_CAVEAT not in sales, "売上 deck over 売上 fact raised a false subject caveat")

    # No facts at all: the deck is honestly blank, so no caveat.
    empty = _html("量子コンピュータのスライドを作って", [])
    add(_CAVEAT not in empty, "an empty deck raised a subject caveat with no facts to misattribute")

    # A request that names no discernible subject: no caveat.
    no_subject = _html("スライドを作って", [_RETENTION])
    add(_CAVEAT not in no_subject, "a subjectless request raised a subject caveat")

    total = 10
    return DeckSubjectResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckSubjectResult", "evaluate_deck_discloses_subject_unmatched"]
