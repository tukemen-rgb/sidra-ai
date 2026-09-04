"""C-1234: the game's tuning-panel form controls are phone-usable.

C-1219 raised the panel's buttons to 48dp, but the difficulty select, the
sliders, the colour picker and the checkboxes stayed 13-27px and rendered at
13.3px - too small to tap and small enough to make iOS zoom on focus. The
shell now floors select/input at 16px and 44px for a coarse pointer and
enlarges the checkboxes, all scoped so the desktop panel is unchanged.
"""

from __future__ import annotations

import re

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.touch_form_controls import evaluate_touch_form_controls


def _coarse_body(html: str) -> str:
    start = re.search(r"@media\s*\(\s*pointer\s*:\s*coarse\s*\)\s*\{", html)
    tail = html[start.end():]
    return tail[: tail.find("</style")]


def test_touch_form_controls_eval_passes():
    result = evaluate_touch_form_controls()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_coarse_query_floors_select_and_input():
    body = _coarse_body(generate_game("魚を釣るゲームを作って").html)
    assert re.search(r"(select|input)[^{}]*\{[^{}]*font-size\s*:\s*16px", body)
    m = re.search(r"(select|input)[^{}]*\{[^{}]*min-height\s*:\s*(\d+)px", body)
    assert m and int(m.group(2)) >= 44
    assert "input[type=checkbox]" in body


def test_button_rule_and_desktop_base_unchanged():
    html = generate_game("シューティングゲームを作って").html
    body = _coarse_body(html)
    # C-1219 button rule preserved.
    assert re.search(r"button\s*\{[^{}]*min-height\s*:\s*48px", body)
    # The 44px floor does not leak to the desktop (non-media) base CSS.
    base = html.split("@media", 1)[0]
    assert not re.search(r"(select|input)[^{}]*\{[^{}]*min-height\s*:\s*44px", base)
