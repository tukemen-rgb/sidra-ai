"""C-1535: on a phone, the finger that plays must not also zoom the page.

The pages wire pointer events, which do not stop the browser's own gestures,
and had no ``touch-action`` at all. Six of the ten templates are played with
the gesture the browser was taking: a double tap (fishing, duel, kaiju) and a
drag (racing, catch, marble).

These assertions read the RESOLVED style out of Chromium, which is what the
filing asked for - a page can carry the property on a selector that matches
nothing, and the HTML looks identical either way.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.browser import chromium_path, computed_styles
from sidra_ai.creation.games import generate_game
from sidra_ai.evals.creation_touch_gestures_guarded import (
    REQUESTS,
    evaluate_creation_touch_gestures_guarded,
)

pytestmark = pytest.mark.skipif(
    chromium_path() is None,
    reason="no browser here; resolved style cannot be read",
)


def test_touch_gestures_eval_passes():
    result = evaluate_creation_touch_gestures_guarded()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 51


@pytest.mark.parametrize("template", sorted(REQUESTS))
def test_the_play_surface_takes_the_gesture(template):
    page = generate_game(REQUESTS[template], template=template)
    styles = computed_styles(
        page.html,
        {"canvas": "canvas", "body": "body"},
        ("touch-action", "user-select", "-webkit-user-select"),
    )
    assert styles is not None
    assert styles["canvas"]["touch-action"] == "none"
    assert "none" in (
        styles["canvas"]["user-select"],
        styles["canvas"]["-webkit-user-select"],
    )
    # ...and the page keeps its own scrolling and pinch zoom: C-1535 says the
    # surrender is scoped to the surface, not taken from the reader.
    assert styles["body"]["touch-action"] == "auto"


def test_the_pad_needs_no_rule_of_its_own():
    """C-1019 draws the pad inside the canvas, so one surface covers both.

    Asserted rather than assumed: a second canvas would mean the pad had
    grown its own element and this rule would stop covering it.
    """

    assert generate_game(REQUESTS["racing"], template="racing").html.count("<canvas") == 1
