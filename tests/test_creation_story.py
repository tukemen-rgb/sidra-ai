"""A scaffolded document that says 〔未記入〕 everywhere reads as finished.

That is the failure this file guards. Headings plus placeholders look like a
deliverable in a directory listing and in a summary; nobody discovers they say
nothing until they open one. So the tests here do not ask whether the files
were written - ``validate_project`` already does - they ask whether what is in
them could only have come from *this* production.

The second theme is the opposite risk. Filling あらすじ with generated prose
would put invented intent where a reader is least likely to check it, so the
plot stays blank *and labelled*, and a test holds that line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation import story  # noqa: E402
from sidra_ai.creation.games import _DIFFICULTY, TEMPLATES  # noqa: E402
from sidra_ai.creation.projects import (  # noqa: E402
    Stage,
    count_substantive_stages,
    scaffold_project,
)


# ------------------------------------------------ the plan is the game's


def test_the_plan_reads_the_request_the_way_the_game_generator_does() -> None:
    """A second parser would describe a game nobody generated."""

    plan = story.plan_for("難しい釣りゲームを作って")

    assert plan.template == "fishing"
    assert plan.difficulty == "hard"
    assert (plan.speed, plan.band) == _DIFFICULTY["fishing"]["hard"]


def test_every_template_has_controls_and_parameter_names() -> None:
    """A template without an entry would print a generic table and pass."""

    for key in TEMPLATES:
        assert story.CONTROLS.get(key), key
        assert story.PARAMETERS.get(key), key


# --------------------------------------------- the documents are specific


def test_the_features_table_carries_the_numbers_the_page_plays() -> None:
    """The whole point: hard in the document is the hard the page runs."""

    plan = story.plan_for("難しい釣りゲームを作って")

    text = story.features("題", (), plan)

    for level in ("easy", "normal", "hard"):
        for value in _DIFFICULTY["fishing"][level]:
            assert str(value) in text


def test_the_controls_table_lists_keys_the_game_actually_binds() -> None:
    text = story.features("題", (), story.plan_for("釣りゲームを作って"))

    assert "SPACE" in text
    assert "← →" not in text, "that is the other template's input"


def test_the_catch_template_gets_its_own_controls() -> None:
    text = story.features("題", (), story.plan_for("キャッチゲームを作って"))

    assert "← →" in text
    assert "SPACE" not in text


def test_structure_names_the_input_rather_than_saying_operate() -> None:
    """A screen table without the key is a heading pretending to be a spec."""

    text = story.structure("題", (), story.plan_for("釣りゲームを作って"))

    assert "SPACE" in text


def test_structure_admits_the_screens_that_do_not_exist_yet() -> None:
    """game.html is one screen. A flow claiming three would be a wish."""

    text = story.structure("題", (), story.plan_for("釣りゲームを作って"))

    assert "単一画面" in text
    assert "まだ無いもの" in text


def test_the_scenario_quotes_the_rules_from_the_generator() -> None:
    plan = story.plan_for("釣りゲームを作って")

    text = story.scenario("題", (), plan)

    assert TEMPLATES["fishing"].how_to_play in text


def test_the_plot_stays_blank_and_says_it_is_blank() -> None:
    """Generated prose here would be invented intent in the worst place."""

    text = story.scenario("題", (), story.plan_for("釣りゲームを作って"))

    assert story.BLANK in text
    assert "生成器は物語を作りません" in text


def test_evidence_is_printed_and_its_absence_is_stated() -> None:
    with_source = story.features("題", ("site docs/DESIGN.md",), story.plan_for("釣り"))
    without = story.features("題", (), story.plan_for("釣り"))

    assert "site docs/DESIGN.md" in with_source
    assert "見つかりませんでした" in without


# ------------------------------------------------------- model overlay


def test_a_model_may_fill_the_plot_it_was_left() -> None:
    plan = story.plan_for("釣りゲームを作って")
    text = story.scenario("題", (), plan)

    filled = story.with_prose(text, "夜明けの堤防。潮が動く前に一本。")

    assert "夜明けの堤防" in filled
    assert story.BLANK not in filled.split("## あらすじ")[1].split("## 登場")[0]


def test_no_model_leaves_the_labelled_blank_standing() -> None:
    """The default configuration has no weights; that must not lose the label."""

    text = story.scenario("題", (), story.plan_for("釣りゲームを作って"))

    assert story.with_prose(text, "   ") == text


# --------------------------------------------------------- the counter


def test_a_whole_project_writes_three_specific_stages(tmp_path) -> None:
    request = "企画から難しい釣りゲームを一通り作って"

    project = scaffold_project(request, tmp_path)

    assert count_substantive_stages(project, story.plan_for(request)) == 3


def test_a_single_stage_request_counts_only_that_stage(tmp_path) -> None:
    """Counting three for a one-file request would make the number free."""

    request = "脚本だけ作って"

    project = scaffold_project(request, tmp_path)

    assert Stage.SCENARIO in project.stages
    assert count_substantive_stages(project, story.plan_for(request)) == 1


def test_a_placeholder_document_does_not_count(tmp_path) -> None:
    """The exact artifact this item replaced has to score zero.

    Without this the meter would pass the version with 〔未記入〕 under every
    heading, which is the thing it exists to detect.
    """

    request = "企画から釣りゲームを一通り作って"
    project = scaffold_project(request, tmp_path)
    for name in ("scenario.md", "structure.md", "features.md"):
        (project.root / name).write_text(
            "# 題 — 見出し\n\n## あらすじ\n\n〔未記入〕\n", encoding="utf-8"
        )

    assert count_substantive_stages(project, story.plan_for(request)) == 0


def test_a_missing_file_does_not_count(tmp_path) -> None:
    request = "企画から釣りゲームを一通り作って"
    project = scaffold_project(request, tmp_path)
    (project.root / "features.md").unlink()

    assert count_substantive_stages(project, story.plan_for(request)) == 2


@pytest.mark.parametrize("template_word", ["釣り", "キャッチ"])
def test_both_templates_reach_three(tmp_path, template_word) -> None:
    request = f"企画から{template_word}ゲームを一通り作って"

    project = scaffold_project(request, tmp_path / template_word)

    assert count_substantive_stages(project, story.plan_for(request)) == 3
