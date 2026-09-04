"""Does a generated deck put each fact on only one slide?

C-1237: build_slides filled every section independently from the whole fact
list, so a fact matching more than one section's cues - or a numeric fact that
also carried a prose cue - appeared on several slides at once. A pitch whose
「解決」 slide and 「根拠となる数字」 slide show the identical paragraph reads as
broken, the same way a report whose 概要 repeated its first fact did (C-1232).
build_slides now claims each fact for the first section that takes it and hides
it from the rest.

The checks build a deck from facts crafted to match two sections each and
confirm no fact's text appears on two slides, while every fact still lands on
some slide and an empty retrieval still leaves honest blanks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DeckNoDuplicateFactsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _slide_texts(deck) -> list[str]:
    # One string per slide: its bullets joined. Sources are not fact text.
    return [" ".join(slide.bullets) for slide in deck.slides]


def evaluate_deck_no_duplicate_facts() -> DeckNoDuplicateFactsResult:
    from sidra_ai.creation.decks import BLANK, generate_deck
    from sidra_ai.creation.evidence import Fact

    checks = 0
    failures: list[str] = []

    # Each fact is written to match two sections at once:
    #  - solves+number: 解決 cue「できる」 and a number -> 解決 and 根拠 both want it
    #  - next+number:  次の一歩 cue「次」 and a number -> 根拠 and 次の一歩 both want it
    solves_number = Fact(
        "検査エンジンは 3 種類の圧縮を展開できる。", "repo docs/a.md"
    )
    next_number = Fact(
        "次の一歩は 5 件のテンプレートを追加すること。", "repo docs/b.md"
    )
    problem = Fact("課題は誘致の弱点に見られること。", "repo docs/c.md")
    facts = [problem, solves_number, next_number]
    deck = generate_deck("検査エンジンの紹介スライドを作って", facts=facts)
    texts = _slide_texts(deck)

    # 1-3: no fact's text appears on more than one slide.
    for fact in facts:
        count = sum(1 for t in texts if fact.text in t)
        if count <= 1:
            checks += 1
        else:
            failures.append(f"{fact.text[:16]}… appears on {count} slides")

    # 4-6: every fact still lands on some slide (dedup did not drop content).
    for fact in facts:
        if any(fact.text in t for t in texts):
            checks += 1
        else:
            failures.append(f"{fact.text[:16]}… vanished from the deck")

    # 7: total distinct fact placements == number of facts (each placed once).
    placements = sum(sum(1 for t in texts if f.text in t) for f in facts)
    if placements == len(facts):
        checks += 1
    else:
        failures.append(f"{placements} placements for {len(facts)} facts")

    # 8: the numeric slide still carries a number (its whole purpose).
    numeric = next((t for s, t in zip(deck.slides, texts) if s.title == "根拠となる数字"), "")
    if re.search(r"\d", numeric):
        checks += 1
    else:
        failures.append("the numeric slide lost its number")

    # 9-10: an empty retrieval still yields honest blanks, not filler.
    empty = generate_deck("紹介スライドを作って", facts=[])
    empty_texts = _slide_texts(empty)
    if all(BLANK in t for t in empty_texts):
        checks += 1
    else:
        failures.append("empty deck: a slide is not blank")
    if not any(re.search(r"\d", t) for t in empty_texts):
        checks += 1
    else:
        failures.append("empty deck: a number appeared from nowhere")

    return DeckNoDuplicateFactsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=10,
        failures=tuple(failures),
    )
