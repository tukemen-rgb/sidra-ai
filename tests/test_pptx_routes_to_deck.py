"""C-1250: a PowerPoint request routes to the deck maker, not a game.

The deck job writes a real .pptx (decks.save_pptx), but 「pptx／パワポ／
PowerPoint」 were missing from the intent detector's deck words, so those
requests came back unknown (weak) and fell to the question path - and
「…の pptx を作って」 built a fishing game. They are deck requests now, while a
game and a report still route where they did.
"""

from __future__ import annotations

from sidra_ai.creation.decks import _title_from
from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.evals.pptx_routes_to_deck import evaluate_pptx_routes_to_deck


def _kind(message: str):
    intent = detect_creation_intent(message)
    return intent.kind if intent.is_creation else None


def test_pptx_routes_to_deck_eval_passes():
    result = evaluate_pptx_routes_to_deck()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_powerpoint_spellings_route_to_deck():
    for req in ("pptx を作って", "パワポを作って", "PowerPoint を作って", "ＰＰＴＸを作って"):
        assert _kind(req) is CreationKind.DECK, req


def test_pptx_subject_is_a_deck_not_a_game():
    assert _kind("GAMEYARD 提案の pptx を作って") is CreationKind.DECK


def test_controls_unmoved():
    assert _kind("釣りゲームを作って") is CreationKind.GAME
    assert _kind("レポートを作って") is CreationKind.DOCUMENT
    assert _kind("スライドを作って") is CreationKind.DECK


def test_pptx_deck_title_is_clean():
    # The deck built from a pptx request is titled by its subject, no kind word
    # and no dangling particle where it was.
    assert _title_from("GAMEYARD 提案の pptx を作って", "既定") == "GAMEYARD 提案"
    assert _title_from("パワポを作って", "SIDRA AI のご提案") == "SIDRA AI のご提案"
