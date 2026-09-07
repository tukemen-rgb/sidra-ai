"""Does a deck's cover title drop the format words the request phrased?

C-1465. A deck's title is taken from the operator's own words, minus the
slide-kind word the artifact already is (C-1249/C-1282: a deck titled
「営業用のデッキ」 would print 「デッキ」 on the very slide that is a deck). But
``_title_from`` stripped the kind word and the trailing particle each exactly
once, so the most natural phrasing - 「会議のスライドをパワポで作って」, which
stacks two kind words with a particle between them - dropped only the outer
word and left 「会議のスライドをパワポ」 on the cover ``<h1>``, the ``<title>``
and the confirmation line: an ungrammatical cover that leaks the tool's name.
The full spelling 「パワーポイント」 was not in the kind list at all.

The fix peels the trailing particle and a trailing kind word repeatedly until
the tail is a real subject, and adds the full 「パワーポイント」 spelling. This
eval drives the real ``generate_deck`` end to end and reads ``deck.title``.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (request, the title the cover must carry). The default cover for the pitch
#: outline, used when the words were only kind/format words.
_DEFAULT = "SIDRA AI のご提案"

# Stacked kind/format words - the outer word is dropped today, the inner is not.
_STACKED = (
    ("会議のスライドをパワポで作って", "会議"),
    ("企画のプレゼンをパワポで作成して", "企画"),
    ("提案資料をpptxで作成して", "提案"),
    ("営業戦略のスライドをパワーポイントで作って", "営業戦略"),
    ("プレゼンの極意をスライドで作って", "プレゼンの極意"),
)

# Single kind word - already correct, must stay correct (no over-stripping).
_SINGLE = (
    ("会議のスライドを作って", "会議"),
    ("営業戦略のスライドを作って", "営業戦略"),
    ("資料設計の指針のスライドを作って", "資料設計の指針"),
)

# Only kind/format words: the outline's default cover is better than a blank
# or a bare 「スライド」/「パワポ」.
_DEFAULTED = (
    ("スライドを作って", _DEFAULT),
    ("パワポで作って", _DEFAULT),
)


@dataclass(frozen=True)
class DeckTitleFormatResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_title_drops_format_words() -> DeckTitleFormatResult:
    from sidra_ai.creation.decks import generate_deck

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request, expected in (*_STACKED, *_SINGLE, *_DEFAULTED):
        title = generate_deck(request).title
        add(title == expected,
            f"title {title!r} != {expected!r} for {request!r}")

    total = len(_STACKED) + len(_SINGLE) + len(_DEFAULTED)
    return DeckTitleFormatResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckTitleFormatResult", "evaluate_deck_title_drops_format_words"]
