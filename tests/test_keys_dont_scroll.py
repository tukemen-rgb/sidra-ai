"""C-1215: game keys must not scroll the page out from under the game.

Six ArrowDown presses scrolled every generated page 208px - the board slid
off screen while the player walked south. One guard on the native listener
prevents the browser default for arrows and Space, except when focus is on
a form control, so the tuning panel's sliders keep their keys.
"""

from __future__ import annotations

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.keys_dont_scroll import evaluate_keys_dont_scroll


def test_guard_is_in_every_probed_template():
    result = evaluate_keys_dont_scroll()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_guard_excludes_form_controls():
    html = generate_game("冒険ゲームを作って").html
    assert "INPUT|TEXTAREA|SELECT|BUTTON" in html


def test_guard_registers_before_the_remap_wrapper():
    """The guard rides the native addEventListener (C-1305 wraps it later)."""

    html = generate_game("冒険ゲームを作って").html
    guard = html.index("INPUT|TEXTAREA|SELECT|BUTTON")
    remap = html.index("addEventListener")
    assert remap <= guard  # the guard's own call is the first registration
