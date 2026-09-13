"""Does renaming a game leave its accent colour alone?

C-1779. ``detect_revision_intent`` scans for an accent-colour adjustment with
``for word, colour in _ACCENT_WORDS.items(): if word in message`` over the whole
message. The accent words are single kanji (赤青緑黄紫橙桃白), which appear
naturally inside a *new title* being set - 「タイトルを『赤い彗星』に変えて」 -
so a rename silently repainted the page's accent. ``_targeting_text`` already
strips the new title when deciding which page is meant; the same reasoning
decides what to change. The accent (and the other panel adjustments) now scan the
message with the new title removed, while a colour named outside a title
(「差し色を赤にして」) still applies and a rename that also names a colour still
does both.

The checks drive ``detect_revision_intent`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.revise import _ACCENT_WORDS, detect_revision_intent

_RED = _ACCENT_WORDS["赤"]
_GREEN = _ACCENT_WORDS["緑"]


@dataclass(frozen=True)
class RevisionAccentResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_revision_rename_does_not_bleed_into_accent() -> RevisionAccentResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def adj(message: str) -> dict:
        return dict(detect_revision_intent(message).adjustments)

    red_title = adj("さっきのゲームのタイトルを「赤い彗星」に変えて")
    blue_title = adj("さっきのゲームのタイトルを「青い鳥」に変えて")
    plain_title = adj("さっきのゲームのタイトルを「城」に変えて")
    colour_ask = adj("さっきのゲームの差し色を赤にして")
    both = adj("さっきのゲームのタイトルを「城」に、差し色を緑にして")

    # --- (A) a colour kanji inside the new title does not repaint ---------
    add("accent" not in red_title,
        f"A: renaming to 「赤い彗星」 bled into the accent: {red_title}")
    # --- (B) the rename itself still applies ------------------------------
    add(red_title.get("title") == "赤い彗星",
        f"B: the rename to 「赤い彗星」 was lost: {red_title}")
    # --- (C) a colour named outside a title still applies -----------------
    add(colour_ask.get("accent") == _RED,
        f"C: 「差し色を赤にして」 no longer recolours: {colour_ask}")
    # --- (D) the same for another colour title ---------------------------
    add("accent" not in blue_title and blue_title.get("title") == "青い鳥",
        f"D: renaming to 「青い鳥」 bled or lost the title: {blue_title}")
    # --- (E) a colourless rename is clean (no false positive) ------------
    add("accent" not in plain_title and plain_title.get("title") == "城",
        f"E: a colourless rename misbehaved: {plain_title}")
    # --- (F) rename + explicit recolour in one message does both ---------
    add(both.get("title") == "城" and both.get("accent") == _GREEN,
        f"F: a combined rename+recolour was broken: {both}")

    total = 6
    return RevisionAccentResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "RevisionAccentResult",
    "evaluate_revision_rename_does_not_bleed_into_accent",
]
