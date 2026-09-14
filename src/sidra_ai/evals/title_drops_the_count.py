"""Is the artifact named after its subject, or after how many were asked for?

C-1833. 「5枚のスライドを作って」 was titled 「5枚」, 「30フレームのGIFを作って」 was
「30フレーム」, and 「魚の3Dモデルを3つ作って」 was 「魚3つ」. Measured across nine
count-bearing requests: eight titles carried the number, and one
(「新商品のスライドを5枚で作って」) kept the kind word too, because the strip that
removes it is anchored to the end and the count sat behind it.

Two loops had been circling this family from opposite sides: C-1822 strips the
length out of a document's title, while C-1821, C-1823 and C-1832 make the
body state the number that was really made. They are complementary - the title
names the subject, the body says what exists - so the stripping side is now
shared by the three generators that lacked it.

The body's notes are checked here too: a title fix that silenced them would
trade one silence for another.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation.decks import generate_deck, slide_count_note
from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.gifs import FRAMES, generate_gif, length_note
from sidra_ai.creation.models3d import count_note, generate_model3d
from sidra_ai.creation.vocabulary import drop_size_phrases

_DIGITS = re.compile(r"\d")


@dataclass(frozen=True)
class TitleCountResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_title_drops_the_count() -> TitleCountResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) the deck ------------------------------------------------------
    deck_titles = {
        request: generate_deck(request).title
        for request in (
            "5枚のスライドを作って",
            "10枚の新商品のスライドを作って",
            "新商品のスライドを5枚で作って",
        )
    }
    add(not any(_DIGITS.search(title) for title in deck_titles.values()),
        f"A: a deck is still named after its size: {deck_titles}")
    # --- (B) the GIF -------------------------------------------------------
    gif_titles = {
        request: generate_gif(request).title
        for request in ("30フレームのGIFを作って", "5秒の魚のGIFを作って")
    }
    add(not any(_DIGITS.search(title) for title in gif_titles.values()),
        f"B: a GIF is still named after its length: {gif_titles}")
    # --- (C) the 3D model --------------------------------------------------
    model_titles = {
        request: generate_model3d(request).title
        for request in ("魚の3Dモデルを3つ作って", "3つの船の3Dモデルを作って")
    }
    add(not any(_DIGITS.search(title) for title in model_titles.values()),
        f"C: a model is still named after its count: {model_titles}")
    # --- (D) and the kind word comes off once the count is gone ------------
    #     This is the C-1829 mechanism: the kind strip is anchored to the end,
    #     so a count behind it turned the rule off entirely.
    add(generate_deck("新商品のスライドを5枚で作って").title == "新商品",
        "D: the kind word still rides along behind the count")
    # --- (E) the 3D generator gets the ADVERB rule too ---------------------
    #     C-1829 widened six generators and missed this one, so 「今すぐ」 was
    #     part of the model's name until now. Held here so the seventh cannot
    #     drift away from the other six again.
    add(generate_model3d("魚の3Dモデルを今すぐ作って").title == "魚",
        "E: the 3D title still carries the request's adverb")
    # --- (F) the body still says what was really made ---------------------
    add(slide_count_note("5枚のスライドを作って", 4) != ""
        and length_note("30フレームのGIFを作って", FRAMES) != ""
        and count_note("魚の3Dモデルを3つ作って") != "",
        "F: the title fix silenced the note that states the real number")
    # --- (G) a request with no count is untouched -------------------------
    add(generate_deck("新商品のスライドを作って").title == "新商品"
        and generate_gif("魚のGIFを作って").title == "魚"
        and generate_model3d("魚の3Dモデルを作って").title == "魚",
        "G: a request that named no count changed its title")
    # --- (H) a number that is not a count, and a word that merely contains
    #         a unit character, are both left alone ------------------------
    add(drop_size_phrases("2026年のゲーム") == "2026年のゲーム"
        and drop_size_phrases("点滅する魚") == "点滅する魚"
        and drop_size_phrases("いつつの星") == "いつつの星",
        "H: the rule cut something that was not a count")
    # --- (I) the document's own rule (C-1822) still stands ----------------
    add(generate_document("2000字の収益化のレポートを作って").title == "収益化",
        "I: the document's length-prefix rule was disturbed")

    return TitleCountResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["TitleCountResult", "evaluate_title_drops_the_count"]
