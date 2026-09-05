"""C-1247: the on-screen pad provides every control the briefing names.

A C-1244 regression: the pad drew only the keys ``keys_read`` reports, and
``keys_read`` missed ``K('ArrowLeft')`` (platformer) and ``partsSteerX``
(kaiju), so those games lost their ◀▶ on a phone while the briefing still said
「← → で歩き／走り」. ``keys_read`` now sees both, so the pad keeps the arrows a
steering game needs - and still omits them from a game (fishing) that has none.
"""

from __future__ import annotations

import re

from sidra_ai.creation.games import generate_game, _script_of
from sidra_ai.creation.touchpad import keys_read
from sidra_ai.evals.pad_covers_briefing_controls import (
    evaluate_pad_covers_briefing_controls,
)


def _pad_active(html: str) -> set[str]:
    m = re.search(r"PAD_ACTIVE\s*=\s*new Set\(\s*\[([^\]]*)\]\s*\)", _script_of(html))
    return set(re.findall(r'"([^"]*)"', m.group(1))) if m else set()


def test_pad_covers_briefing_controls_eval_passes():
    result = evaluate_pad_covers_briefing_controls()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_kaiju_pad_has_walk_buttons():
    # kaiju walks via partsSteerX; the pad must offer ◀▶ (and A to shoot).
    active = _pad_active(generate_game("怪獣 を作って").html)
    assert {"ArrowLeft", "ArrowRight", " "} <= active, active


def test_platformer_pad_has_run_buttons():
    # platformer runs via K('ArrowLeft'/'ArrowRight'); the pad must offer ◀▶.
    active = _pad_active(generate_game("横スクロール を作って").html)
    assert {"ArrowLeft", "ArrowRight"} <= active, active


def test_keys_read_sees_helper_and_steer_forms():
    kaiju = _script_of(generate_game("怪獣 を作って").html)
    plat = _script_of(generate_game("横スクロール を作って").html)
    assert {"ArrowLeft", "ArrowRight"} <= keys_read(kaiju)
    assert {"ArrowLeft", "ArrowRight"} <= keys_read(plat)


def test_fishing_pad_still_has_no_arrows():
    # The fix must not over-detect: fishing steers nothing, so no ◀▶▲▼.
    active = _pad_active(generate_game("釣り を作って").html)
    assert "ArrowLeft" not in active and "ArrowUp" not in active
    assert " " in active  # cast is still there
