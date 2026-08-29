"""The pad has to be pressable, and it has to keep out of the way.

Two failures are equally quiet. A pad that is drawn but sends nothing leaves
a phone with a picture of controls; a pad that swallows every tap breaks the
canvas gestures the templates already had. Both pages open and run, so only
these tests notice.
"""

from __future__ import annotations

from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html
from sidra_ai.creation.touchpad import (
    ALIASES,
    BUTTON_CSS_PX,
    GAP_CSS_PX,
    PAD_KEYS,
    keys_read,
    unreachable_keys,
)


def test_every_template_carries_the_pad_and_still_runs():
    for key in TEMPLATES:
        page = generate_game("ゲームを作って", template=key).html
        assert "drawPad" in page, key
        # Present is not enough: the wiring has to survive the JS checker,
        # or the pad would have taken the game down with it.
        assert validate_game_html(page)["playable"], key


def test_every_key_a_template_reads_has_a_button():
    for key, spec in TEMPLATES.items():
        assert unreachable_keys(spec.script) == set(), key


def test_the_pad_meets_the_touch_target_floor():
    # docs/research/game-design-notes.md §4: 48dp targets, 8dp apart.
    assert BUTTON_CSS_PX >= 48
    assert GAP_CSS_PX >= 8


def test_key_names_fold_to_one_control_per_button():
    # adventure stores keys lowercased; duel compares them as written. If
    # these read as different controls, the coverage check reports a missing
    # button that is right there on screen.
    assert keys_read("keys['arrowleft']") == keys_read("e.key==='ArrowLeft'")
    assert keys_read("e.key==='r'") == keys_read("e.key==='R'")
    assert keys_read("e.code==='Space'") == {" "}


def test_wasd_counts_as_the_arrows_rather_than_four_more_buttons():
    for alias, real in ALIASES.items():
        assert real in PAD_KEYS
        assert keys_read(f"keys['{alias}']") == {real}


def test_a_template_with_a_key_the_pad_cannot_send_is_reported():
    # The guard's whole job: a new control added to a template without a
    # button has to show up as unreachable rather than pass unnoticed.
    assert unreachable_keys("if(e.key==='z'){bomb()}") == {"z"}


def test_the_pad_does_not_replace_the_keyboard():
    page = generate_game("ゲームを作って", template="catch").html
    # The template's own keyboard handler is still the thing that moves the
    # basket; the pad sends events into it rather than around it.
    assert "addEventListener('keydown'" in page
    assert "new KeyboardEvent" in page


def test_the_pad_hides_itself_on_a_mouse():
    page = generate_game("ゲームを作って", template="fishing").html
    assert "pointer:coarse" in page


def test_a_pad_press_does_not_also_fire_the_canvas_gesture():
    # fishing casts on any canvas tap and catch tracks pointermove. Without
    # this, pressing left on the D-pad would also cast, or drag the basket.
    page = generate_game("ゲームを作って", template="fishing").html
    assert "stopImmediatePropagation" in page
