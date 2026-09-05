"""C-1244: the on-screen touch pad draws only the buttons the game uses.

The pad drew all six buttons (◀▶▲▼ + A + R) on every template, so the default
fishing game (one control: SPACE) put four dead directional buttons over a
352×158px play field on a phone. ``padButtons`` now filters by a ``PAD_ACTIVE``
set built from the keys the finished page reads, so a template that reads only
space shows A (and R) and leaves the D-pad's space to the game.
"""

from __future__ import annotations

import re

from sidra_ai.creation.games import TEMPLATES, generate_game, _script_of
from sidra_ai.creation.touchpad import PAD_KEYS, keys_read
from sidra_ai.evals.pad_only_used_buttons import (
    _parse_pad_active,
    evaluate_pad_only_used_buttons,
)


def test_pad_only_used_buttons_eval_passes():
    result = evaluate_pad_only_used_buttons()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


def test_fishing_pad_drops_the_dead_dpad():
    # Fishing reads one control (space). The pad shows A (space) and R, and
    # none of the four directional buttons that used to cover the band.
    script = _script_of(generate_game("釣りゲームを作って").html)
    active = _parse_pad_active(script)
    assert active == {" ", "r"}, active
    assert "ArrowLeft" not in active
    assert "ArrowUp" not in active


def test_pad_filters_by_pad_active():
    # Without the filter a correct PAD_ACTIVE would be inert.
    script = _script_of(generate_game("釣りゲームを作って").html)
    assert "PAD_ACTIVE.has(" in script


def test_every_genre_draws_exactly_its_used_pad_keys():
    pad = set(PAD_KEYS)
    for genre in sorted(TEMPLATES):
        script = _script_of(generate_game(f"{genre} を作って").html)
        active = _parse_pad_active(script)
        assert active is not None, f"{genre}: no PAD_ACTIVE declared"
        assert active == (keys_read(script) & pad), genre


def test_directional_genres_keep_their_buttons():
    # A genre that reads the arrows must still show them - the fix removes dead
    # buttons, never live ones.
    script = _script_of(generate_game("横スクロールアクションを作って").html)
    active = _parse_pad_active(script)
    # platformer reads at least left/right/jump; whatever it reads, no arrow it
    # uses may be missing from the pad.
    used = keys_read(script) & set(PAD_KEYS)
    assert used <= active
