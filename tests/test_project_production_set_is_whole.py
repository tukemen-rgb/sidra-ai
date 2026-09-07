"""C-1462: 「制作一式」 builds the whole production, not one stage.

「制作一式」 (the project generator's own offered label) was not a whole-project
word, so a subject word colliding with a stage cue (新機能→機能) narrowed the
full-set request to one file. It now forces the whole production; 「アセット一式」
stays its own stage.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.projects import STAGE_ORDER, Stage, requested_stages
from sidra_ai.evals.project_production_set_is_whole import (
    evaluate_project_production_set_is_whole,
)


def test_project_whole_eval_passes():
    result = evaluate_project_production_set_is_whole()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


@pytest.mark.parametrize(
    "request_text",
    [
        "新機能ローンチのゲーム制作一式を作って",
        "モデルルーム管理ゲームの制作一式を作って",
        "ゲーム制作一式を作って",
    ],
)
def test_production_set_builds_all_stages(request_text):
    assert requested_stages(request_text) == STAGE_ORDER


def test_asset_set_stays_its_own_stage():
    assert requested_stages("ゲームのアセット一式を作って") == (Stage.ASSETS,)


def test_single_stage_request_still_narrows():
    assert requested_stages("ゲームの脚本だけ作って") == (Stage.SCENARIO,)
