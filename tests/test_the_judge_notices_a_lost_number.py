"""C-1491: the judge stopped a number that got worse, and not one that left.

``compare()`` walked the *new* snapshot and asked, of each key it found,
whether it had moved. A key that was no longer there was never visited. So
deleting a check - or letting it fall to ``unmeasurable`` - produced
``([], [])``: exit 1 on its own, which merges honestly as ``[記録]``, and
**exit 0 and a clean merge** if the same commit moved any other outcome.
The number that was the evidence for a finished item could disappear
without a word.

The board's own guard, ``test_every_metric_the_backlog_names_exists``,
covers the keys the board names by hand. That was 33 when this was filed,
against 357 in the script.

``_RETIRED`` is the escape hatch, and it is deliberate: without a way to
retire a number on purpose, the first legitimate retirement would put
pressure on the check itself.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "product_metrics_c1491", Path(__file__).resolve().parents[1] / "scripts" / "product_metrics.py"
)
assert _SPEC is not None and _SPEC.loader is not None
pm = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = pm
_SPEC.loader.exec_module(pm)


def _metric(key: str, value: float, kind: str, direction: str = "up"):
    return pm.Metric(key, key, value, kind=kind, direction=direction)


TABLE = {
    "kept": _metric("kept", 1.0, pm.OUTCOME),
    "watched": _metric("watched", 10.0, pm.OUTCOME),
    "guarded": _metric("guarded", 0.0, pm.GUARD, "down"),
    "noise": _metric("noise", 5.0, pm.CONTEXT),
}
BEFORE = {k: {"value": m.value, "kind": m.kind} for k, m in TABLE.items()}


def _snap(**values):
    return {k: {"value": v, "kind": TABLE[k].kind} for k, v in values.items()}


def _broken(after, table=None) -> dict[str, object]:
    _, broke = pm.compare(BEFORE, after, TABLE if table is None else table)
    return {m.key: m for m in broke}


WITHOUT_WATCHED = {k: v for k, v in TABLE.items() if k != "watched"}


# --- the two directions ----------------------------------------------


def test_a_number_that_was_deleted_is_a_regression() -> None:
    """The hard case: the metric object is gone too, so there is nothing
    left to ask about it - which is why the old loop could not see it."""

    lost = _broken(_snap(kept=1.0, guarded=0.0, noise=5.0), WITHOUT_WATCHED)

    assert "watched" in lost
    assert lost["watched"].gone is True
    assert lost["watched"].before == 10.0


def test_a_number_that_can_no_longer_answer_is_a_regression() -> None:
    lost = _broken(_snap(kept=1.0, watched=None, guarded=0.0, noise=5.0))

    assert "watched" in lost
    assert lost["watched"].gone is False


def test_a_guard_that_disappears_is_a_regression() -> None:
    """A vanished 「zero missed credentials」 is not a passing guard."""

    assert "guarded" in _broken(_snap(kept=1.0, watched=10.0, noise=5.0))


def test_the_run_exits_two_and_says_which_number_left(capsys) -> None:
    """End to end through the real reporter, because the exit code is the
    verdict every loop reads."""

    class _Collector:
        metrics = [TABLE["kept"], TABLE["guarded"], TABLE["noise"]]

    assert pm._report(BEFORE, _Collector()) == 2
    printed = capsys.readouterr().out
    assert "watched" in printed
    assert "消えた" in printed
    assert "_RETIRED" in printed, "the reader is not told how to retire a number"


# --- and the controls, so it is not "call everything a regression" ----


def test_an_unchanged_run_is_not_a_regression() -> None:
    assert _broken(BEFORE) == {}


def test_an_improvement_is_not_a_regression() -> None:
    assert _broken(_snap(kept=1.0, watched=11.0, guarded=0.0, noise=5.0)) == {}


def test_a_context_number_may_disappear() -> None:
    """`Metric` says context is a count of our own writing and cannot be
    evidence that something outside changed, so it cannot block a merge."""

    assert _broken(_snap(kept=1.0, watched=10.0, guarded=0.0)) == {}


def test_a_number_that_never_answered_loses_nothing() -> None:
    was_blank = dict(BEFORE, watched={"value": None, "kind": pm.OUTCOME})
    _, broke = pm.compare(
        was_blank, _snap(kept=1.0, guarded=0.0, noise=5.0), WITHOUT_WATCHED
    )

    assert broke == []


def test_a_retirement_written_down_is_allowed() -> None:
    pm._RETIRED["watched"] = "the thing it measured stopped existing (test)"
    try:
        assert _broken(_snap(kept=1.0, guarded=0.0, noise=5.0), WITHOUT_WATCHED) == {}
    finally:
        del pm._RETIRED["watched"]


def test_the_retirement_table_carries_a_reason() -> None:
    """An empty string would make the table a list of keys somebody wanted
    gone, which is the argument it exists to force into writing."""

    for key, reason in pm._RETIRED.items():
        assert isinstance(reason, str) and reason.strip(), key


# --- and the real script is subject to it -----------------------------


def test_the_shipped_metric_reports_both_directions() -> None:
    """The judge measures the shipped `compare()`, not a copy of it: this
    test and the metric would otherwise be able to disagree."""

    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "product_metrics.py"
    ).read_text(encoding="utf-8")
    body = source.split('"judge_notices_a_lost_number"')[0].rsplit(
        "--- and the judge notices a number that stopped answering", 1
    )[-1]

    assert '"judge_notices_a_lost_number"' in source
    # The metric drives the shipped function rather than re-implementing the
    # rule, so the metric and these tests cannot drift into disagreeing.
    assert "compare(_lost_before" in body or "compare(_was_blank" in body
    assert "_RETIRED" in body, "the retirement escape hatch is measured too"
