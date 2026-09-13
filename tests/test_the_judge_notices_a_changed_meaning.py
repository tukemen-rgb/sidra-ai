"""C-1763: the judge held both sides of the detail and never read either.

Third of a family. C-1491 was a number that vanished; C-1707 was two
snapshots taken on different footings; this is a number that held still
while the words beside it began describing something else. All three had
their evidence sitting in the snapshot, and all three were invisible
because ``compare`` only ever looked at values.

It is not hypothetical. C-1751 bundled four probes whose ``continue`` meant
"this template is not measured"; the worker returned no gaps, the caller
read that as a pass, and two metrics started saying ten templates were
driven when seven were. Every value held. ``--compare`` printed NO
MOVEMENT and it merged. A person diffing details found it a cycle later.

Deliberately not wired to the exit code: details quote live seconds and
counts, so they move for honest reasons. This prints and a person decides.
Measured before it was written - the same tree twice moves one detail of
459, and three real commits moved 1, 1 and 3, where the 3 was the defect.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "product_metrics_c1763",
    Path(__file__).resolve().parents[1] / "scripts" / "product_metrics.py",
)
assert _SPEC is not None and _SPEC.loader is not None
pm = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = pm
_SPEC.loader.exec_module(pm)


def _snap(**entries):
    return {pm._ENV_KEY: pm._env_mark(), **entries}


def _entry(value, detail, kind=None):
    return {"value": value, "unit": "", "kind": kind or pm.OUTCOME, "detail": detail}


def test_a_detail_that_changed_under_a_still_number_is_named() -> None:
    """The C-1751 shape, exactly."""

    before = _snap(shipped=_entry(1.0, "4 型を実走行"))
    after = _snap(shipped=_entry(1.0, "10 型を実走行"))

    said = pm.changed_meanings(before, after)

    assert [key for key, _, _ in said] == ["shipped"]
    assert said[0][1] == "4 型を実走行", "the claim that was there is half the evidence"
    assert said[0][2] == "10 型を実走行", "and the claim that replaced it is the other half"


def test_a_key_whose_value_moved_is_not_listed_here() -> None:
    """The movement lines already say so. Repeating it would bury the one
    case this section exists for."""

    before = _snap(shipped=_entry(1.0, "4 型を実走行"))
    after = _snap(shipped=_entry(3.0, "10 型を実走行"))

    assert pm.changed_meanings(before, after) == []


def test_an_unchanged_comparison_says_nothing() -> None:
    before = _snap(shipped=_entry(1.0, "4 型を実走行"), held=_entry(2.0, "同じ", pm.GUARD))

    assert pm.changed_meanings(before, dict(before)) == []


def test_a_key_on_only_one_side_is_not_a_changed_meaning() -> None:
    """Arriving and leaving are different findings with their own lines -
    C-1491 owns the leaving, and it stops a merge. Counting either here
    would report the same event twice under a heading that never fails."""

    before = _snap(gone=_entry(1.0, "was here"))
    after = _snap(fresh=_entry(1.0, "is here"))

    assert pm.changed_meanings(before, after) == []


def test_the_environment_mark_is_not_a_metric() -> None:
    before = _snap(shipped=_entry(1.0, "same"))
    after = dict(before)
    after[pm._ENV_KEY] = {"python": "3.99.0", "executable": "/elsewhere", "venv": False}

    assert pm.changed_meanings(before, after) == []


def _verdict(before, collector, after):
    real = pm._snapshot
    pm._snapshot = lambda _c: after
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = pm._report(before, collector)
    finally:
        pm._snapshot = real
    return code, out.getvalue()


class _Collector:
    def __init__(self, *metrics):
        self.metrics = list(metrics)
        self.timings = []


def test_the_verdict_is_untouched_by_a_changed_detail() -> None:
    """This must never decide a merge. A detail is not evidence."""

    before = _snap(shipped=_entry(1.0, "4 型を実走行"))
    after = _snap(shipped=_entry(1.0, "10 型を実走行"))
    collector = _Collector(
        pm.Metric("shipped", "shipped", 1.0, kind=pm.OUTCOME, detail="10 型を実走行")
    )

    code, said = _verdict(before, collector, after)

    assert code == 1, "a detail must not turn NO MOVEMENT into anything else"
    assert "NO MOVEMENT" in said
    assert "shipped" in said, "and the reader still has to be told"
    assert "4 型を実走行" in said and "10 型を実走行" in said


def test_a_real_movement_still_reads_the_same() -> None:
    """The other direction: nothing about the existing verdicts moved."""

    before = _snap(shipped=_entry(1.0, "same words"))
    after = _snap(shipped=_entry(4.0, "same words"))
    collector = _Collector(
        pm.Metric("shipped", "shipped", 4.0, kind=pm.OUTCOME, detail="same words")
    )

    code, said = _verdict(before, collector, after)

    assert code == 0
    assert "MOVED: 1 outcome number(s)." in said
    assert "held still while their detail changed" not in said
