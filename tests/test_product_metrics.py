"""The completion condition is only as real as the instrument behind it.

`docs/BACKLOG.md` says an item is done when an external number moves, and
names those numbers by key. That is prose until something checks that the
keys exist and that measuring them still works - the same lesson gap 11
records about the false-positive rate, which was measured for weeks without
anything enforcing it.

So: the metric keys the backlog promises must be the metric keys the script
produces, and the script must actually run.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "product_metrics.py"
BACKLOG = ROOT / "docs" / "BACKLOG.md"

sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="module")
def metrics():
    import product_metrics

    return {m.key: m for m in product_metrics.collect().metrics}


def test_every_metric_the_backlog_names_exists(metrics) -> None:
    """A backlog item cannot promise to move a number nobody measures."""

    named = set(
        re.findall(r"→ 動かす数字: `([a-z0-9_]+)`", BACKLOG.read_text(encoding="utf-8"))
    )
    assert named, "the backlog no longer tags items with the number they move"
    assert named <= set(metrics), sorted(named - set(metrics))


def test_no_probe_crashed(metrics) -> None:
    """A probe that raised reports as unmeasurable and would hide a zero."""

    broken = {k: m.detail for k, m in metrics.items() if k.endswith("_probe")}
    assert not broken, broken


def test_the_numbers_that_matter_are_measured(metrics) -> None:
    """Pin the usability numbers specifically.

    These are the ones that stayed at zero while the queue emptied. If a
    future change drops them from the table, the completion condition
    quietly reverts to counting commits.
    """

    for key in ("ask_without_json", "index_visible", "conversation_turns"):
        assert metrics[key].value is not None, key


def test_script_runs_and_prints_a_table() -> None:
    """Exercised as an operator would, not imported."""

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )

    assert result.returncode == 0, result.stderr
    assert "Done means one of these moved" in result.stdout


def test_json_output_is_machine_readable() -> None:
    import json

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "ask_without_json" in payload
