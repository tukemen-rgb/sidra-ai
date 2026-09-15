"""C-1857: the pad-contrast judge measures all of its rule, not a tenth.

§4 増築 (WCAG 1.4.11) holds the pad's boundary to 3:1 against the floor it is
drawn over, on every template, theme and act. The check ran on catch alone -
12 of 120 cells - and found the floor by the spelling 「sky:scenePaint」, which
adventure and puzzle do not use. The product was healthy throughout (120 cells,
worst 4.44); the instrument was looking at a tenth of it, and the worst cell
was in one of the two templates it could not read.

The threshold assertions below feed KNOWN-BAD colours rather than trusting the
sweep to be red. Against a healthy product a deleted comparison changes
nothing - every cell passes either way - so deletion cannot be detected by the
sweep, and only an input that must fail proves the comparison is wired. That
is the same trap as a cap no input ever reaches.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import TEMPLATES
from sidra_ai.evals.pad_visible_every_floor import (
    ACTS,
    FLOOR_RATIO,
    THEME_SUFFIXES,
    _FLOOR,
    _ratio,
    evaluate_pad_visible_every_floor,
)


def test_pad_visible_eval_passes():
    result = evaluate_pad_visible_every_floor()
    assert result.failures == ()
    assert result.cells == len(TEMPLATES) * len(THEME_SUFFIXES) * ACTS == 120


def test_the_sample_is_the_whole_rule():
    """Every template, not the one that happened to be typed in the loop."""

    result = evaluate_pad_visible_every_floor()
    assert result.cells == len(TEMPLATES) * len(THEME_SUFFIXES) * ACTS


def test_the_floor_is_found_by_the_paint_not_by_its_key():
    """Both spellings the pages actually use.

    「sky:scenePaint」 is one family's; adventure and puzzle assign the paint
    straight to fillStyle, and a pattern that wanted the key read them as
    having no floor at all.
    """

    assert _FLOOR.search("sky:scenePaint('#0a0f1c')")
    assert _FLOOR.search("cx.fillStyle = scenePaint('#05070f')")
    assert _FLOOR.search("c.fillStyle=scenePaint('#123456')")
    # ...and it still wants a paint, not any six hex digits on the page.
    assert not _FLOOR.search("cx.fillStyle = '#0a0f1c'")


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_reports_a_floor(template):
    """No template may be silently unmeasurable.

    A cell nobody measured must not read as a cell that passed - which is
    what the narrow pattern would have caused the moment the loop widened.
    """

    from sidra_ai.creation.games import generate_game
    from sidra_ai.evals.pad_visible_every_floor import _SCRIPT

    html = generate_game("ゲームを作って", template=template).html
    script = _SCRIPT.search(html)
    assert script
    assert _FLOOR.search(script.group(1)), template


def test_the_threshold_rejects_what_it_should():
    """Known-bad input, because a healthy sweep cannot prove a live check."""

    # A boundary the same colour as its floor is invisible by definition.
    assert _ratio("#0a0f1c", "#0a0f1c") == pytest.approx(1.0)
    assert _ratio("#0a0f1c", "#0a0f1c") < FLOOR_RATIO
    # Near-black on near-black: the 1.05:1 border-on-raised case C-1388 found.
    assert _ratio("#16243a", "#0a0f1c") < FLOOR_RATIO
    # ...and the pair the fix relies on clears it on that same floor.
    assert _ratio("#dfe7f5", "#0a0f1c") >= FLOOR_RATIO
    assert FLOOR_RATIO == 3.0
