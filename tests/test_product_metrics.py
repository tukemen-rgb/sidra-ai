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


def _measured_keys(metrics) -> set[str]:
    """Every name an outcome number is measured under, across both instruments.

    `product_metrics.py` is not the whole registry. It runs offline in seconds,
    so the numbers that need the four external checkouts are measured
    elsewhere: `check_answerable_regression.py` (which also enforces floors)
    and `check_boss_questions.py` (which has no floors yet - its series starts
    at its first run). Reading only the first one would call a promise about
    `answerable_*` unmeasured when it is in fact the better-guarded half.
    """

    import check_answerable_regression
    import check_boss_questions

    return (
        set(metrics)
        | set(check_answerable_regression.METRIC_KEYS)
        | set(check_boss_questions.DIRECTION)
    )


def test_every_metric_the_backlog_names_exists(metrics) -> None:
    """A backlog item cannot promise to move a number nobody measures."""

    named = set(
        re.findall(r"→ 動かす数字: `([a-z0-9_]+)`", BACKLOG.read_text(encoding="utf-8"))
    )
    measured = _measured_keys(metrics)
    assert named, "the backlog no longer tags items with the number they move"
    assert named <= measured, sorted(named - measured)


def test_answerable_metric_names_track_the_floors() -> None:
    """A floor with no name cannot be promised; a name with no floor guards nothing."""

    import check_answerable_regression as car

    floors = {name for name in dir(car) if name.startswith("MIN_")}
    assert len(car.METRIC_KEYS) == len(floors), sorted(car.METRIC_KEYS) + sorted(floors)


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


def test_the_paraphrase_detail_is_derived_not_copied(metrics) -> None:
    """A number pasted into a report has nothing keeping it honest.

    This line read "(last measured 0/7)" for a day after the question set grew
    to 26 and a paraphrase question began retrieving. It is read to decide
    whether the paraphrase problem still exists, so being stale there is worse
    than being absent. It now quotes the enforced floor, which CI fails on when
    it stops matching.
    """
    import check_answerable_regression as answerable

    detail = metrics["answerable_paraphrase"].detail
    assert f"floor: {answerable.MIN_PARAPHRASE}" in detail
    assert "last measured" not in detail, "a measurement was copied back in"
