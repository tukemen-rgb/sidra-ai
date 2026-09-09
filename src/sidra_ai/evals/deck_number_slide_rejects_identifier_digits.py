"""Does the deck's number slide reject a digit that only names a thing?

C-1609. A pitch's 「根拠となる数字」 slide (and a status deck's 「測った数字」)
is chosen by :meth:`Fact.mentions_number`, and that asked only whether any
digit ran anywhere in the text. The corpus is saturated with identifiers that
carry digits but no quantity - ``BM25``, ``FTS5``, ``GPT-6``, backlog ids like
``C-1234``, ``S3`` - so a capability sentence whose only "number" was the 25 in
``BM25`` landed on the evidence slide, the one slide of a proposal whose whole
point is a figure. The reader saw 「SIDRA は BM25 の純Python検索…」 filed as a
supporting number, which reads as padding and defeats the deck's own promise
that 「数字は索引した文書から引いたものだけを載せ」る.

The fix masks an identifier's digits before looking for a figure. A digit that
follows an ASCII letter (across at most one hyphen) is part of a name; a digit
that does not is a quantity. So a real figure - 14/38, 512 MiB, 60Hz, 3件,
80.0%, and 「GPT4は月20万円」 where only ``GPT4`` is a name - still counts, while
the identifiers do not.

The checks build real ``generate_deck`` outputs and read the number slide, and
exercise ``Fact.mentions_number`` directly on the boundary cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import BLANK, generate_deck
from sidra_ai.creation.evidence import Fact

#: A capability sentence whose only digits are the 25 inside 「BM25」.
_IDENT_FACT = Fact("SIDRA は BM25 の純 Python 検索で外部埋め込みに依存しない。",
                   "docs/ARCHITECTURE.md")
#: A sentence carrying a real figure.
_METRIC_FACT = Fact("回答可能率は 14/38 だった。", "docs/OUTCOMES.md")


@dataclass(frozen=True)
class DeckNumberSlideResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _slide_text(deck, title: str) -> str:
    for slide in deck.slides:
        if slide.title == title:
            return " ".join(slide.bullets)
    return ""


def evaluate_deck_number_slide_rejects_identifier_digits() -> DeckNumberSlideResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- deck placement: the identifier fact stays off the number slide ---
    pitch_ident = generate_deck("提案スライドを作って", facts=[_IDENT_FACT], outline="pitch")
    add(BLANK in _slide_text(pitch_ident, "根拠となる数字"),
        "pitch: an identifier-only fact was placed on 根拠となる数字")

    pitch_metric = generate_deck("提案スライドを作って", facts=[_METRIC_FACT], outline="pitch")
    add("14/38" in _slide_text(pitch_metric, "根拠となる数字"),
        "pitch: a real figure did not reach 根拠となる数字")

    status_ident = generate_deck("進捗報告のスライドを作って", facts=[_IDENT_FACT], outline="status")
    add(BLANK in _slide_text(status_ident, "測った数字"),
        "status: an identifier-only fact was placed on 測った数字")

    status_metric = generate_deck("進捗報告のスライドを作って", facts=[_METRIC_FACT], outline="status")
    add("14/38" in _slide_text(status_metric, "測った数字"),
        "status: a real figure did not reach 測った数字")

    # --- mentions_number: an identifier's digit is not a figure ---
    for text in ("C-1234 を起票した。", "FTS5 に昇格した。", "GPT-6 と S3 を評価した。"):
        add(not Fact(text, "x").mentions_number(),
            f"identifier read as a number: {text!r}")

    # --- mentions_number: a real quantity still counts ---
    add(Fact("3 件の不具合が残っている。", "x").mentions_number(),
        "a plain count stopped counting as a number")
    # CJK boundary: only 「GPT4」 is a name; the 20万円 figure must survive.
    add(Fact("GPT4は月20万円かかる。", "x").mentions_number(),
        "a figure glued after an identifier by CJK text was lost")
    add(Fact("512 MiB・60Hz・80.0% を測った。", "x").mentions_number(),
        "a unit-bearing figure stopped counting as a number")

    total = 10
    return DeckNumberSlideResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DeckNumberSlideResult",
    "evaluate_deck_number_slide_rejects_identifier_digits",
]
