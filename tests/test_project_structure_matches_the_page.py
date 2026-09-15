"""C-1848: the production document describes the page that shipped.

It said 「現状の game.html は単一画面です。タイトル画面もリザルト画面も無く」 and
listed both under 「まだ無いもの」, after C-1033's briefing gate, the recap strip
and attract mode had all arrived.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation import attract, recap, startscreen
from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.story import ProductionPlan, plan_for, screens, structure
from sidra_ai.evals.project_structure_matches_the_page import (
    evaluate_project_structure_matches_the_page,
)

_TEMPLATES = sorted(TEMPLATES)


def _document(template: str) -> str:
    plan = plan_for(f"{template}のゲームを作って")
    return structure("題", (), ProductionPlan(template, plan.difficulty, plan.speed, plan.band))


def test_project_structure_eval_passes():
    result = evaluate_project_structure_matches_the_page()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


@pytest.mark.parametrize("template", _TEMPLATES)
def test_the_document_lists_the_start_screen(template):
    assert "開始（ブリーフィング）" in _document(template)


@pytest.mark.parametrize("template", _TEMPLATES)
def test_the_page_really_has_a_briefing(template):
    html = generate_game(f"{template}のゲーム", template=template).html
    assert any(line in html for line in startscreen.BRIEFINGS[template])


@pytest.mark.parametrize("template", _TEMPLATES)
def test_the_document_does_not_deny_screens_that_exist(template):
    document = _document(template)
    assert "単一画面" not in document
    assert "タイトル画面（開始ボタン" not in document
    assert "リザルト画面（最終スコア" not in document


@pytest.mark.parametrize("template", _TEMPLATES)
def test_attract_and_losing_state_are_reported_per_template(template):
    document = _document(template)
    assert ("アトラクト" in document) == (template in attract.ATTRACT_TEMPLATES)
    assert ("結果表示（負け）" in document) == (template in recap.LOSS_WIRED)


def test_what_is_genuinely_missing_is_still_said():
    # Difficulty comes from the words of the request; no screen offers it.
    assert "難易度選択" in _document("fishing")
    assert not any(
        "難易度" in line
        for lines in startscreen.BRIEFINGS.values()
        for line in lines
    )


@pytest.mark.parametrize("template", _TEMPLATES)
def test_the_flow_line_and_the_table_agree(template):
    document = _document(template)
    plan = plan_for(f"{template}のゲームを作って")
    for name, _shows, _advance in screens(
        ProductionPlan(template, plan.difficulty, plan.speed, plan.band)
    ):
        assert document.count(name) >= 2
