"""Does the deck flatten Markdown in its slide bullets, like answer and report?

C-1289 (the deck twin of C-1288): ``_bullets_for`` trimmed evidence to whole
sentences but never ran it through ``evidence.plain_text``. The corpus is
Markdown, so a fact carrying 「## 概況」, bold, a link or a table put raw 「##」/
「**」/「[…](url)」/「| --- |」 on an HTML slide as literal characters - worse than
in the .md report, since HTML does not render them. The deck now flattens first:
decoration becomes prose, a table reads as 「セル / セル；」, figures survive.

The checks build a real deck from Markdown-laden numeric facts and read the HTML.
"""

from __future__ import annotations

from dataclasses import dataclass

_REQUEST = "新機能ローンチの週次進捗のプレゼン資料を作って"


def _facts():
    from sidra_ai.creation.evidence import Fact

    return [
        Fact(text="## 概況\n登録は **1,240 件** で [詳細](https://example.com/r) を参照。",
             source="r:docs/a.md"),
        Fact(text="| 指標 | 値 |\n| --- | --- |\n| 率 | 63% |", source="r:docs/b.md"),
    ]


@dataclass(frozen=True)
class DeckEvidencePlainResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_evidence_plain_text() -> DeckEvidencePlainResult:
    from sidra_ai.creation.decks import generate_deck, validate_deck

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    facts = _facts()
    deck = generate_deck(_REQUEST, facts=facts)
    html = deck.html

    # 1: no raw Markdown decoration reaches an HTML slide.
    add("##" not in html, "a raw heading 「##」 leaked onto a slide")
    add("**" not in html, "raw bold 「**」 leaked onto a slide")
    add("](" not in html, "a raw Markdown link 「](url)」 leaked onto a slide")
    add("| ---" not in html, "a raw table separator 「| --- |」 leaked onto a slide")

    # 2: the flatten keeps the figures the slide is there to show, and the deck
    #    still passes its own validator (every number on a slide is in evidence).
    add("1,240" in html and "63%" in html, "a figure was lost in the flatten")
    add(validate_deck(deck, facts)["usable"], "the deck failed validation after the flatten")

    # 3: the table became prose rather than bars.
    add("／" in html or " / " in html or "；" in html,
        "the table was not flattened to prose")

    total = 7
    return DeckEvidencePlainResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckEvidencePlainResult", "evaluate_deck_evidence_plain_text"]
