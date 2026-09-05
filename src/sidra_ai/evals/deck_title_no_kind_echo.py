"""Does a deck's cover echo the word 「スライド」 the request already said?

C-1249 (the deck twin of C-1246): ``decks._title_from`` kept the whole request
phrase before the make-verb, so 「GAMEYARD の強みのスライドを作って」 titled the
deck 「GAMEYARD の強みのスライド」 - a stack of slides whose cover slide and
``<title>`` say 「スライド」. The cover should name the subject alone
(「GAMEYARD の強み」). 「営業用のデッキ」「進捗のプレゼン」「紹介スライドショー」
were the same.

The checks build decks from requests that do and do not end in a slide-kind
word and confirm the trailing kind word is dropped from ``deck.title`` (and so
from the rendered ``<h1>``/``<title>``), that a request with no kind word is
untouched, and that a bare 「スライドを作って」 falls back to the deck's default
title rather than an empty cover.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Slide-deck-kind nouns a cover title should not end with. Longer forms first
#: so the whole word is stripped (スライドショー before スライド).
_KINDS = (
    "スライドショー",
    "プレゼンテーション",
    "ピッチデッキ",
    "スライド",
    "プレゼン",
    "デッキ",
    "ピッチ",
)


@dataclass(frozen=True)
class DeckTitleNoKindEchoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_title_no_kind_echo() -> DeckTitleNoKindEchoResult:
    from sidra_ai.creation.decks import generate_deck

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: a 「…のスライド」 request titles the deck by its subject only, in both
    # the model title and the rendered cover.
    deck = generate_deck("GAMEYARD の強みのスライドを作って")
    add(deck.title == "GAMEYARD の強み", f"title kept the kind word: 「{deck.title}」")
    add(
        "<h1>GAMEYARD の強み</h1>" in deck.html
        and "の強みのスライド</h1>" not in deck.html,
        "the rendered cover still doubles the kind word",
    )

    # 2: other kinds are stripped too.
    add(generate_deck("営業用のデッキを作って").title == "営業用",
        "デッキ not stripped")
    add(generate_deck("進捗のプレゼンを作って").title == "進捗",
        "プレゼン not stripped")
    add(generate_deck("紹介スライドショーを作って").title == "紹介",
        "スライドショー not stripped (longest-match)")

    # 3: a request with no kind word is left exactly as it was.
    add(generate_deck("新機能を作って").title == "新機能",
        "a non-kind title changed")

    # 4: a bare kind word falls back to the outline's default title, not "".
    bare = generate_deck("スライドを作って")
    add(bool(bare.title.strip()) and bare.title != "スライド",
        f"bare kind word did not fall back: 「{bare.title}」")

    # 5: the cover never ends in a kind word for a kind-word request - a guard
    # across the whole list, anchored to the tail.
    bad = [k for k in _KINDS if generate_deck(f"今月{k}を作って").title.endswith(k)]
    add(not bad, f"these kinds survived at the title end: {bad}")

    # 6: a kind word that is part of the subject, not its tail, is kept - the
    # strip is anchored to the end, not a match-anywhere that would maul
    # 「スライド設計の指針」 into 「設計の指針」.
    add(generate_deck("スライド設計の指針を作って").title == "スライド設計の指針",
        "a mid-phrase kind word was stripped")

    return DeckTitleNoKindEchoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=9,
        failures=tuple(failures),
    )


__all__ = ["DeckTitleNoKindEchoResult", "evaluate_deck_title_no_kind_echo"]
