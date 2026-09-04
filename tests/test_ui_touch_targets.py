"""C-1224: the ask page's buttons must be tappable on a phone.

On an iPhone-sized screen the 更新 button and every per-file 開く download
button were 41-42px tall, under the 48dp tap minimum. C-1219 fixed the game
shell; this is the product page behind it. One coarse-pointer rule lifts
every button without touching the desktop layout.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_touch_targets import evaluate_ui_touch_targets


def test_ui_touch_targets_eval_passes():
    result = evaluate_ui_touch_targets()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_coarse_pointer_button_rule_present():
    assert re.search(
        r"@media\s*\(\s*pointer:\s*coarse\s*\)\s*\{\s*button\s*\{\s*min-height:\s*48px",
        ASK_PAGE,
    )


def test_min_height_does_not_leak_to_desktop_button_rule():
    # The unconditional `button { ... }` rule must not carry a min-height.
    base = ASK_PAGE.split("button {", 1)[1].split("}", 1)[0]
    assert "min-height" not in base
