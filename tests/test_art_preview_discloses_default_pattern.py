"""C-1284: the generated art page discloses the flow default it fell back to.

A request that names no pattern is drawn with the flow default. The chat summary
says so (C-1271), but the HTML - opened in a browser and forwarded - was titled
by the subject over a flow drawing with no word of it, the silent artifact
C-1281/C-1283 fixed for the report and the 3D preview. The page now carries a
disclosure note under the caption when the pattern was a default.
"""

from __future__ import annotations

from sidra_ai.creation.art import generate_art, validate_art
from sidra_ai.evals.art_preview_discloses_default_pattern import (
    evaluate_art_preview_discloses_default_pattern,
)

_NOTE_MARK = '<p class="note">'


def test_art_preview_discloses_default_pattern_eval_passes():
    result = evaluate_art_preview_discloses_default_pattern()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_fallback_page_discloses_the_flow_default():
    art = generate_art("猫のアートを作って")
    assert art.pattern == "flow" and not art.pattern_named
    assert _NOTE_MARK in art.html
    assert "既定の「フロー」" in art.html
    assert all(p in art.html for p in ("フロー", "軌道"))
    assert "<title>猫</title>" in art.html


def test_named_pattern_page_carries_no_note():
    for req, pattern in (("波のアートを作って", "flow"),
                         ("軌道のアートを作って", "orbits")):
        art = generate_art(req)
        assert art.pattern == pattern and art.pattern_named
        assert _NOTE_MARK not in art.html


def test_note_has_no_fabricated_number_and_page_valid():
    art = generate_art("犬のアートを作って")
    note = art.html.split(_NOTE_MARK, 1)[1].split("</p>", 1)[0]
    assert not any(ch.isdigit() for ch in note)
    assert validate_art(art)["valid"]
