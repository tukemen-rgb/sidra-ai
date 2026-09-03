"""C-1219: a generated game's control-panel buttons must be tappable on a phone.

The touch pad made the game itself playable on a phone, but the HTML panel
around it (skin picker, copy-result, key remap, reset) kept buttons 24-32px
tall - under the 48dp minimum the knowledge base the pad cites already sets.
No panel sets a button height inline, so one coarse-pointer rule in the
shared shell raises every one of them without touching the desktop layout
or the canvas-drawn pad.
"""

from __future__ import annotations

import re

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.touch_targets import evaluate_touch_targets


def test_touch_targets_eval_passes():
    result = evaluate_touch_targets()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_coarse_pointer_button_rule_present_in_every_template():
    # The rule lives in the shared shell, so it rides every template.
    for request in ("魚を釣るゲーム", "猫がジャンプするゲーム", "パズルを作って", "シューティングを作って"):
        html = generate_game(request).html
        assert "@media (pointer:coarse)" in html
        assert re.search(r"@media\s*\(pointer:coarse\)\s*\{button\{min-height:48px\}", html)


def test_min_height_does_not_leak_to_desktop():
    html = generate_game("魚を釣るゲーム").html
    without_coarse = re.sub(
        r"@media\s*\(pointer:coarse\)\s*\{[^@]*?\}\}", "", html, flags=re.DOTALL
    )
    style = without_coarse.split("</style>")[0]
    assert "min-height" not in style
