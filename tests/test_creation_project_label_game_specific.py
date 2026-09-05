"""C-1263: the unbuildable decline calls PROJECT what it is - game production.

C-1261's decline labelled the project kind 「企画一式」, so 「新規事業の企画を
作って」 was declined while the same message offered 「企画一式」 - a contradiction.
PROJECT builds a game-production bundle, so the label is now 「ゲーム制作一式」.
"""

from __future__ import annotations

import tempfile

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.creation_project_label_game_specific import (
    evaluate_creation_project_label_game_specific,
)


def _service() -> SidraService:
    return SidraService(Settings(data_dir=tempfile.mkdtemp(prefix="proj-label-test-")))


def test_creation_project_label_game_specific_eval_passes():
    result = evaluate_creation_project_label_game_specific()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_decline_names_project_as_game_production():
    answer = _service().chat("Excelを作って")["answer"]
    assert "ゲーム制作一式" in answer
    # No bare 「企画一式」 that would invite any plan request.
    assert "企画一式" not in answer.replace("ゲーム制作一式", "")


def test_business_plan_request_declined_without_false_offer():
    answer = _service().chat("新規事業の企画を作って")["answer"]
    assert "作れません" in answer
    assert "ゲーム制作一式" in answer
    assert "企画一式" not in answer.replace("ゲーム制作一式", "")


def test_real_project_request_still_builds():
    answer = _service().chat("企画から作って")["answer"]
    assert "制作一式" in answer
    assert "作れません" not in answer
