"""C-1779: renaming a game leaves its accent colour alone.

detect_revision_intent scanned the accent colour over the whole message; the
accent words are single kanji (赤青緑…) common inside a new title, so a rename
silently repainted the accent. The adjustment scans now read the message with
the new title removed, while a colour named outside a title still applies and a
rename that also names a colour still does both.
"""

from __future__ import annotations

from sidra_ai.creation.revise import _ACCENT_WORDS, detect_revision_intent
from sidra_ai.evals.revision_rename_does_not_bleed_into_accent import (
    evaluate_revision_rename_does_not_bleed_into_accent,
)


def _adj(message: str) -> dict:
    return dict(detect_revision_intent(message).adjustments)


def test_revision_accent_eval_passes():
    result = evaluate_revision_rename_does_not_bleed_into_accent()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_rename_with_a_colour_word_does_not_repaint():
    adj = _adj("さっきのゲームのタイトルを「赤い彗星」に変えて")
    assert adj.get("title") == "赤い彗星"
    assert "accent" not in adj


def test_a_colour_named_outside_a_title_still_applies():
    adj = _adj("さっきのゲームの差し色を赤にして")
    assert adj.get("accent") == _ACCENT_WORDS["赤"]


def test_rename_and_recolour_in_one_message_does_both():
    adj = _adj("さっきのゲームのタイトルを「城」に、差し色を緑にして")
    assert adj.get("title") == "城"
    assert adj.get("accent") == _ACCENT_WORDS["緑"]
