"""A production is a directory, and it holds exactly what was asked for.

The two failures worth guarding are opposite and equally easy to write:
scaffolding everything (which buries "脚本だけ作って"), and claiming stages
that never reached the disk (which an operator only discovers later). Both
have tests here, and the second is checked against the filesystem rather than
against the summary, because the summary is the part a broken scaffolder
still gets right.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.creation.project_job import build_project_generator
from sidra_ai.creation.projects import (
    STAGE_ORDER,
    Stage,
    requested_stages,
    scaffold_project,
    slugify,
    validate_project,
)

PINNED = datetime(2026, 8, 26, 19, 0, 0, tzinfo=timezone.utc)


def test_a_whole_production_writes_every_stage(tmp_path: Path) -> None:
    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)

    assert project.stages == STAGE_ORDER
    assert validate_project(project)["complete"]
    on_disk = {entry.name for entry in project.root.iterdir()}
    assert on_disk == {
        "scenario.md",
        "structure.md",
        "features.md",
        "assets",
        "game.html",
        "production-log.md",
    }


def test_a_single_stage_request_writes_only_that_stage(tmp_path: Path) -> None:
    """The failure mode of a scaffolder: giving six files to someone who asked for one."""

    project = scaffold_project("宇宙ゲームの脚本だけ作って", tmp_path, now=PINNED)

    assert project.stages == (Stage.SCENARIO,)
    assert {entry.name for entry in project.root.iterdir()} == {"scenario.md"}


@pytest.mark.parametrize(
    "request_text, stages",
    [
        ("構成を作って", (Stage.STRUCTURE,)),
        ("機能設定を作って", (Stage.FEATURES,)),
        ("スプライトを作って", (Stage.ASSETS,)),
        ("脚本と構成を作って", (Stage.SCENARIO, Stage.STRUCTURE)),
    ],
)
def test_named_stages_are_the_ones_produced(request_text: str, stages) -> None:
    assert requested_stages(request_text) == stages


def test_a_request_naming_nothing_still_gets_the_whole_production() -> None:
    """Silence is not a narrowing instruction."""

    assert requested_stages("ゲームを作って") == STAGE_ORDER


def test_a_whole_production_request_routes_to_project_not_game() -> None:
    """Both kinds' words appear in the same sentence; PROJECT has to win.

    Routing this to the game generator would hand back a playable page and
    silently drop the scenario, structure, features, art and record the
    operator asked for - a wrong answer that looks like a right one.
    """

    assert detect_creation_intent("釣りゲームを企画から作って").kind is CreationKind.PROJECT
    assert detect_creation_intent("釣りゲームを作って").kind is CreationKind.GAME


def test_two_titles_in_the_same_second_do_not_share_a_directory(tmp_path: Path) -> None:
    """The collision this module shipped with, caught on its first run.

    Japanese titles carry no ASCII, so both slugged to ``project-<stamp>``
    and the second request wrote into the first one's directory.
    """

    first = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    second = scaffold_project("宇宙ゲームの脚本だけ作って", tmp_path, now=PINNED)

    assert first.root != second.root


def test_the_same_request_at_the_same_second_is_the_same_path() -> None:
    """Deterministic, so a caller can find what it just wrote."""

    assert slugify("釣りゲーム", stamp="X") == slugify("釣りゲーム", stamp="X")
    assert slugify("釣りゲーム", stamp="X") != slugify("宇宙ゲーム", stamp="X")


def test_the_game_stage_is_a_real_playable_page(tmp_path: Path) -> None:
    """Not an empty placeholder: the generator for it already exists."""

    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)

    html = (project.root / "game.html").read_text(encoding="utf-8")
    assert "<canvas" in html
    assert "<script>" in html


def test_evidence_is_recorded_as_paths_only(tmp_path: Path) -> None:
    """The log names where things came from, never what they said."""

    facts = [Fact("索引した文書が 1326 件ある", "owner/repo docs/OUTCOMES.md")]
    project = scaffold_project("ゲームを企画から作って", tmp_path, facts=facts, now=PINNED)

    log = (project.root / "production-log.md").read_text(encoding="utf-8")
    assert "owner/repo docs/OUTCOMES.md" in log
    assert "1326" not in log


def test_a_missing_stage_is_reported_rather_than_claimed(tmp_path: Path) -> None:
    """Delete one file and the verdict has to notice.

    Without this, `validate_project` could be returning ``complete`` for
    everything and every other test here would still pass.
    """

    project = scaffold_project("ゲームを企画から作って", tmp_path, now=PINNED)
    (project.root / "features.md").unlink()

    verdict = validate_project(project)

    assert not verdict["complete"]
    assert verdict["missing"] == ["features.md"]


def test_the_generator_names_the_files_it_wrote(tmp_path: Path) -> None:
    generate = build_project_generator(tmp_path)
    request = "釣りゲームを企画から作って"

    outcome = generate(request, detect_creation_intent(request))

    assert outcome.handled
    assert outcome.details["missing"] == []
    assert "scenario.md" in outcome.summary
    assert Path(outcome.artifact_path).is_dir()
