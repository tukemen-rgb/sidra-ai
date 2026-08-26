"""A generation leaves a record, and the record can be found again.

Three promises from C-999, each with the failure it guards against:

* **The log records the run** - time, files, evidence paths, parameters -
  and the record parses back, because a format only a human can check is a
  format whose regressions only a human notices.
* **The record never carries retrieved text.** Paths and parameters only;
  the log reads as metadata and metadata gets pasted places.
* **A project is traceable from the browser's listing** - slug, files, and
  any file downloadable by exactly the name the listing printed - without
  the listing or the download route becoming a hole out of the directory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidra_ai.api.artifacts import (
    ArtifactNotFound,
    list_projects,
    read_project_file,
)
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.projects import scaffold_project
from sidra_ai.creation.records import (
    LOG_NAME,
    RECORDS_HEADING,
    append_record,
    read_records,
)

PINNED = datetime(2026, 8, 26, 20, 0, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------ the record


def test_a_whole_production_records_when_what_evidence_and_parameters(
    tmp_path: Path,
) -> None:
    facts = [Fact("索引した文書が 1326 件ある", "owner/repo docs/OUTCOMES.md")]
    project = scaffold_project(
        "釣りゲームを企画から作って", tmp_path, facts=facts, now=PINNED
    )

    records = read_records(project.root)

    assert len(records) == 1
    record = records[0]
    assert record.when == "2026-08-26T20:00:00Z"
    assert "game.html" in record.made and LOG_NAME in record.made
    assert record.evidence == ("owner/repo docs/OUTCOMES.md",)
    assert record.parameters["template"]
    assert record.parameters["difficulty"]
    assert float(record.parameters["speed"]) > 0


def test_the_record_carries_the_evidence_path_but_never_its_text(
    tmp_path: Path,
) -> None:
    """The one failure this file must never trade away."""

    facts = [Fact("索引の中身 9481 を写してはいけない", "owner/repo docs/OUTCOMES.md")]
    project = scaffold_project(
        "釣りゲームを企画から作って", tmp_path, facts=facts, now=PINNED
    )

    log = (project.root / LOG_NAME).read_text(encoding="utf-8")

    assert "owner/repo docs/OUTCOMES.md" in log
    assert "9481" not in log


def test_a_partial_project_stays_partial_with_no_log_created(tmp_path: Path) -> None:
    """The record rule never overrides the partial-request rule."""

    project = scaffold_project("宇宙ゲームの脚本だけ作って", tmp_path, now=PINNED)

    assert {entry.name for entry in project.root.iterdir()} == {"scenario.md"}
    assert read_records(project.root) == []


def test_appending_beside_a_missing_log_is_refused(tmp_path: Path) -> None:
    """``append_record`` never creates files behind the scaffolder's back."""

    with pytest.raises(FileNotFoundError):
        append_record(tmp_path, made=["x"], evidence=[], parameters={})


def test_a_second_run_appends_a_second_line_in_order(tmp_path: Path) -> None:
    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    append_record(
        project.root,
        made=["assets/player.svg"],
        evidence=[],
        parameters={"seed": 7},
        now=datetime(2026, 8, 26, 21, 0, 0, tzinfo=timezone.utc),
    )

    records = read_records(project.root)

    assert [record.when for record in records] == [
        "2026-08-26T20:00:00Z",
        "2026-08-26T21:00:00Z",
    ]
    assert records[1].made == ("assets/player.svg",)
    assert (project.root / LOG_NAME).read_text(encoding="utf-8").count(
        RECORDS_HEADING
    ) == 1


def test_field_text_cannot_forge_extra_fields(tmp_path: Path) -> None:
    """Separators and newlines in values are stripped, not trusted.

    A title is operator text; a value carrying `` | 根拠: `` or a newline
    would otherwise end the record early or write a second one.
    """

    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    append_record(
        project.root,
        made=["a|b.md"],
        evidence=["evil\npath | 根拠: fake"],
        parameters={"note": "x|y\nz"},
        now=PINNED,
    )

    records = read_records(project.root)

    assert len(records) == 2
    forged = records[1]
    assert "|" not in "".join(forged.made)
    assert all("\n" not in source for source in forged.evidence)


# --------------------------------------------------------- traceability


def test_the_listing_names_the_project_and_its_files(tmp_path: Path) -> None:
    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    (project.root / "assets" / "player.svg").write_text("<svg></svg>")

    listed = {p.slug: p for p in list_projects(tmp_path)}

    assert project.slug in listed
    names = {artifact.name for artifact in listed[project.slug].files}
    assert LOG_NAME in names
    assert "game.html" in names
    assert "assets/player.svg" in names


def test_the_listing_carries_metadata_never_content(tmp_path: Path) -> None:
    scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)

    listing = [p.to_dict() for p in list_projects(tmp_path)]

    assert "<canvas" not in str(listing)
    entry = listing[0]["files"][0]
    assert set(entry) == {"name", "bytes", "modified"}


def test_a_symlinked_project_or_file_is_not_listed(tmp_path: Path) -> None:
    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    outside = tmp_path / "secret.txt"
    outside.write_text("private")
    (project.root / "link.md").symlink_to(outside)
    (project.root.parent / "evil-project").symlink_to(tmp_path)

    listed = {p.slug: p for p in list_projects(tmp_path)}

    assert "evil-project" not in listed
    assert "link.md" not in {a.name for a in listed[project.slug].files}


def test_a_project_file_reads_back_by_its_listed_name(tmp_path: Path) -> None:
    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    (project.root / "assets" / "player.svg").write_text("<svg></svg>")

    payload, name = read_project_file(tmp_path, project.slug, "assets/player.svg")

    assert payload == b"<svg></svg>"
    assert name == "player.svg"


@pytest.mark.parametrize(
    "name",
    [
        "../scenario.md",
        "../../secret.txt",
        "assets/../../secret.txt",
        "/etc/passwd",
        "",
        ".hidden",
        "assets//x.svg",
    ],
)
def test_paths_that_leave_the_project_are_refused(tmp_path: Path, name: str) -> None:
    project = scaffold_project("釣りゲームを企画から作って", tmp_path, now=PINNED)
    (tmp_path / "secret.txt").write_text("private")

    with pytest.raises(ArtifactNotFound):
        read_project_file(tmp_path, project.slug, name)


def test_an_unknown_slug_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ArtifactNotFound):
        read_project_file(tmp_path, "no-such-project", LOG_NAME)
