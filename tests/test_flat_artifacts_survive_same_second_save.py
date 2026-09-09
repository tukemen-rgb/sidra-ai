"""C-1509: a same-second second save must not overwrite the first artifact.

The flat generators stamp names to the second, so two saves of one kind inside
one second collided; unconditional writes lost the first. Each saver now routes
through ``unique_path``, matching the serial-suffix guard ``save_game`` already
had.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from sidra_ai.creation import gifs
from sidra_ai.creation.artifact_paths import unique_path
from sidra_ai.creation.gifs import generate_gif, save_gif
from sidra_ai.evals.flat_artifacts_survive_same_second_save import (
    evaluate_flat_artifacts_survive_same_second_save,
)

_FIXED = datetime(2026, 9, 9, 2, 15, 30, tzinfo=timezone.utc)


def test_flat_artifact_collision_eval_passes():
    result = evaluate_flat_artifacts_survive_same_second_save()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_unique_path_adds_serial_on_collision(tmp_path: Path):
    first = unique_path(tmp_path, "gif-pulse-STAMP", ".gif")
    assert first.name == "gif-pulse-STAMP.gif"
    first.write_bytes(b"one")
    second = unique_path(tmp_path, "gif-pulse-STAMP", ".gif")
    assert second.name == "gif-pulse-STAMP-2.gif"
    second.write_bytes(b"two")
    third = unique_path(tmp_path, "gif-pulse-STAMP", ".gif")
    assert third.name == "gif-pulse-STAMP-3.gif"
    # The originals are untouched.
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"


def test_two_gifs_in_one_second_both_survive(tmp_path: Path):
    with mock.patch.object(gifs, "datetime") as m:
        m.now.return_value = _FIXED
        p1 = save_gif(generate_gif("猫のGIFを作って"), tmp_path)
        p2 = save_gif(generate_gif("海のGIFを作って"), tmp_path)
    assert p1 != p2
    assert p1.exists() and p2.exists()
    files = sorted((tmp_path / "artifacts").glob("gif-*.gif"))
    assert len(files) == 2
