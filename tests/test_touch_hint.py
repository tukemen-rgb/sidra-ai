"""C-1229: a generated game must tell a phone user it can be played by touch.

The how-to named only keyboard keys (「← →」), which a phone lacks, and the
on-screen pad appears only once play starts. The shell now carries a
coarse-pointer hint naming the pad, hidden on the desktop.
"""

from __future__ import annotations

import re

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.touch_hint import evaluate_touch_hint


def test_touch_hint_eval_passes():
    result = evaluate_touch_hint()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_hint_present_and_coarse_gated_in_every_template():
    for request in ("魚を釣るゲーム", "パズルを作って", "シューティングを作って", "猫がジャンプするゲーム"):
        html = generate_game(request).html
        assert 'class="touchhint"' in html, request
        assert ".touchhint{display:none" in html, request
        assert re.search(
            r"@media\s*\(pointer:coarse\)\s*\{\s*\.touchhint\{display:block\}", html
        ), request


def test_hint_names_touch_not_more_keys():
    html = generate_game("魚を釣るゲーム").html
    m = re.search(r'class="touchhint">([^<]*)<', html)
    assert m and "画面のボタン" in m.group(1)
