"""C-1851: a deck bullet says when the 120-char cap truncated a long fact.

The deck-bullet member of the truncation-honesty family (C-1264 for the citation
excerpt, C-1217/C-1849 for numbers). ``whole_sentences`` trims a multi-sentence
slice to a clean end, but a single long clause with no 。 in the cap comes back as
the raw cut whole, so the bullet ended mid-clause - 「…2024年度には 1,23」 - reading
as whole and cutting a figure mid-digit with no 「…」. Such a bullet is now marked,
a split figure is dropped first, and a whole sentence / short fact is untouched.
"""

from __future__ import annotations

import re

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_bullet_marks_truncation import (
    evaluate_deck_bullet_marks_truncation,
)

_LONG = "ユーザー定着率の継続的な改善であり"


def _bullet(fact_text: str) -> str:
    deck = generate_deck("GAMEYARD のスライドを作って", facts=[Fact(fact_text, "owner/repo docs/x.md")])
    for raw in re.findall(r"<li>(.*?)</li>", deck.html, re.S):
        text = re.sub(r"<[^>]+>", "", raw)
        if "主要課題" in text:
            return text
    return ""


def test_deck_bullet_eval_passes():
    result = evaluate_deck_bullet_marks_truncation()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 12


def test_long_clause_bullet_is_marked_and_not_mid_number():
    bullet = _bullet("主要課題は" + _LONG * 6 + "2024年度には 1,234,567,890 円規模")
    assert bullet.endswith("…")
    assert not (len(bullet) >= 2 and bullet[-2].isdigit())
    assert "主要課題" in bullet


def test_whole_sentence_bullet_is_not_marked():
    bullet = _bullet("主要課題は定着率である。" + "詳細は別途に記載する。" * 15)
    assert bullet.endswith("。")
    assert "…" not in bullet


def test_short_fact_is_unchanged():
    assert _bullet("主要課題は定着率である。") == "主要課題は定着率である。"
