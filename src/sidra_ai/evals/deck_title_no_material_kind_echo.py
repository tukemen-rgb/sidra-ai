"""Does a deck's cover echo 「資料」, the everyday word for a deck?

C-1282 (the 資料 gap in C-1249): the intent detector routes every 「X資料」 to
DECK - 「プレゼン資料」「企画資料」「週次進捗資料」, and bare 「資料」 - but
``decks._TITLE_KIND_SUFFIX`` stripped スライド/プレゼン/デッキ and missed the
「資料」 forms, so 「…のプレゼン資料を作って」 titled the deck 「…のプレゼン資料」:
a stack of slides whose cover slide and ``<title>`` say 「プレゼン資料」. The
document title already strips 「資料」; only the deck had missed it.

The pure-kind compounds (「プレゼン資料」 is two kind words stacked) strip whole,
bare 「資料」 handles 「企画資料」→「企画」, and a bare 「資料を作って」 falls back
to the outline's default title. A 「資料」 inside the subject (「資料設計の指針」)
is kept - the strip is anchored to the tail.

Checks build real decks with ``generate_deck`` so the rendered ``<h1>``/``<title>``
are what is judged, not only the model title field.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Pure-kind 資料 compounds a cover must never end with, and bare 資料.
_MATERIAL_KINDS = (
    "プレゼンテーション資料",
    "プレゼン資料",
    "スライド資料",
    "パワポ資料",
    "資料",
)


@dataclass(frozen=True)
class DeckTitleNoMaterialResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_title_no_material_kind_echo() -> DeckTitleNoMaterialResult:
    from sidra_ai.creation.decks import generate_deck

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: a 「…のプレゼン資料」 request titles the deck by its subject only, in
    # both the model title and the rendered cover (two kind words stacked, so
    # the compound must strip whole - not leave 「プレゼン」 behind).
    deck = generate_deck("新機能ローンチの週次進捗のプレゼン資料を作って")
    add(deck.title == "新機能ローンチの週次進捗",
        f"title kept a material kind word: 「{deck.title}」")
    add(
        "<h1>新機能ローンチの週次進捗</h1>" in deck.html
        and "資料</h1>" not in deck.html,
        "the rendered cover still echoes 「資料」",
    )

    # 2: each pure-kind compound falls back to the default title, with no kind
    # word left over - stripping 「資料」 off 「スライド資料」 down to 「スライド」
    # would just echo a different kind word, so the whole compound must go.
    _RESIDUE = ("資料", "スライド", "プレゼン", "デッキ", "パワポ", "ピッチ")
    for phrase in ("プレゼン資料", "プレゼンテーション資料", "スライド資料"):
        title = generate_deck(f"{phrase}を作って").title
        add(bool(title.strip()) and not any(k in title for k in _RESIDUE),
            f"bare 「{phrase}」 did not fall back cleanly: 「{title}」")

    # 3: a real subject before 「資料」 is kept, the kind noun dropped.
    add(generate_deck("企画資料を作って").title == "企画", "「企画資料」 not stripped to 「企画」")
    add(generate_deck("週次進捗資料を作って").title == "週次進捗",
        "「週次進捗資料」 not stripped to 「週次進捗」")

    # 4: a 「資料」 inside the subject, not its tail, is kept - the strip is
    # anchored to the end, not a match-anywhere.
    add(generate_deck("資料設計の指針を作って").title == "資料設計の指針",
        "a mid-phrase 「資料」 was stripped")

    # 5: the cover never ends in a material kind word for such a request - a
    # guard across the whole list, anchored to the tail.
    bad = [k for k in _MATERIAL_KINDS
           if generate_deck(f"今月{k}を作って").title.endswith(k)]
    add(not bad, f"these material kinds survived at the title end: {bad}")

    # 6: the スライド-family strip (C-1249) still works - this fix extends it,
    # it does not replace it.
    add(generate_deck("GAMEYARD の強みのスライドを作って").title == "GAMEYARD の強み",
        "the C-1249 スライド strip regressed")

    total = 10
    return DeckTitleNoMaterialResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DeckTitleNoMaterialResult",
    "evaluate_deck_title_no_material_kind_echo",
]
