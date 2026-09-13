"""C-1786: the art HTML page says a requested colour was not applied.

The palette is fixed to the brand, so 「青い…」 is drawn in cyan/magenta. The chat
summary said so (C-1272) and the page already self-discloses the pattern default
(C-1284), but the colour caveat lived only in the chat summary. The page now
carries it too, alongside the pattern note.
"""

from __future__ import annotations

from sidra_ai.creation.art import generate_art
from sidra_ai.evals.art_page_discloses_color_not_applied import (
    evaluate_art_page_discloses_color_not_applied,
)

_COLOR_NOTE = "配色に反映していません"


def test_art_page_color_eval_passes():
    result = evaluate_art_page_discloses_color_not_applied()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_colour_request_page_discloses_non_application():
    html = generate_art("青い螺旋のアートを作って").html
    assert _COLOR_NOTE in html
    assert "固定の配色" in html
    assert "既定の" in html  # the pattern-default note still coexists


def test_colourless_request_adds_no_colour_note():
    html = generate_art("螺旋のアートを作って").html
    assert _COLOR_NOTE not in html


def test_named_pattern_colour_request_still_discloses_colour():
    html = generate_art("青い軌道のアートを作って").html
    assert _COLOR_NOTE in html
    assert "既定の" not in html  # a named pattern shows no default note
