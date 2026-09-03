"""C-1209: revision sidecars are hidden from the listing, not deleted.

Every generation wrote ``game-*.html`` plus ``game-*.meta.json`` (the
C-1112 revision record) and the ask page listed both - half the rows were
157-byte JSON files that read as gibberish when clicked. The listing now
shows deliverables only; the sidecar file itself stays on disk, stays
downloadable by name, and the revise path's own glob never used the
listing in the first place.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.artifacts import list_artifacts, read_artifact
from sidra_ai.evals.artifact_listing import evaluate_artifact_listing


@pytest.fixture
def data_dir(tmp_path) -> Path:
    directory = tmp_path / "artifacts"
    directory.mkdir()
    (directory / "game-shooter-1.html").write_text("<!doctype html>", encoding="utf-8")
    (directory / "game-shooter-1.meta.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_sidecars_are_not_listed(data_dir: Path):
    names = [artifact.name for artifact in list_artifacts(data_dir)]
    assert names == ["game-shooter-1.html"]


def test_sidecars_stay_downloadable_by_name(data_dir: Path):
    body, _ = read_artifact(data_dir, "game-shooter-1.meta.json")
    assert body == b"{}"


def test_artifact_listing_eval_passes():
    result = evaluate_artifact_listing()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4
