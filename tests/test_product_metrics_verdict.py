"""The completion test is only as honest as its classification of numbers.

`scripts/product_metrics.py` decides whether an iteration counted as
progress. The failure that matters here is not a crash: it is a verdict that
says something moved when nothing did. A loop that can reach "done" without
changing anything outside will keep reporting done long after it has stopped
producing, and every report will be technically true - which is the exact
failure the old commit-based condition had.

Three properties carry that weight.

Context counts must never register as movement. `gate_must_catch_cases` rises
when someone writes a case; `retrieval_cases_synthetic` rises when someone
writes a question. Both are worth doing and neither is evidence that anything
outside this repository changed.

Guards that hold must never register either. Zero external API cost is a
solved problem, structurally enforced. Re-passing it every iteration is not
new progress.

Drift must not register. `gate_false_positive_rate` is a rate, which resists
inflation better than a count but does not escape it: it fell from 10.6% to
10.2% on the morning of 2026-08-19 purely because loops added clean documents
to the denominator. Nothing about the gate improved. That drift was bankable
as "a number moved" until the floor existed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    name = "product_metrics"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Register before executing: ``@dataclass`` resolves a class's own module
    # out of ``sys.modules`` and fails on a module that is not there yet.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pm = _load()


def _metric(key, value, kind, **kwargs):
    return pm.Metric(key, key, value, kind=kind, **kwargs)


METRICS = {
    m.key: m
    for m in (
        _metric("ask_without_json", 0, pm.OUTCOME),
        _metric("gate_false_positive_rate", 10.2, pm.OUTCOME, unit="%",
                direction="down", min_move=0.5),
        _metric("external_api_cost_usd", 0, pm.GUARD, direction="down"),
        _metric("retrieval_mrr", 1.0, pm.GUARD),
        _metric("gate_must_catch_cases", 20, pm.CONTEXT),
    )
}


def _snapshot(**overrides):
    values = {
        "ask_without_json": 0,
        "gate_false_positive_rate": 10.2,
        "external_api_cost_usd": 0,
        "retrieval_mrr": 1.0,
        "gate_must_catch_cases": 20,
    }
    values.update(overrides)
    return {k: {"value": v} for k, v in values.items()}


def _compare(before, after):
    return pm.compare(before, after, METRICS)


def test_an_unchanged_run_is_not_progress():
    moved, broken = _compare(_snapshot(), _snapshot())
    assert moved == []
    assert broken == []


def test_writing_our_own_test_cases_is_not_progress():
    """The gameable move: add a case, watch a number rise, call it done."""
    moved, broken = _compare(_snapshot(), _snapshot(gate_must_catch_cases=25))
    assert moved == [], "a context count was accepted as progress"
    assert broken == []


def test_a_guard_that_holds_is_not_progress():
    moved, _ = _compare(_snapshot(), _snapshot())
    assert not any(METRICS[m.key].kind == pm.GUARD for m in moved)


def test_shipping_a_capability_is_progress():
    moved, broken = _compare(_snapshot(), _snapshot(ask_without_json=1))
    assert broken == []
    assert [(m.key, m.before, m.after) for m in moved] == [("ask_without_json", 0, 1)]


def test_losing_a_capability_fails_the_run():
    moved, broken = _compare(_snapshot(ask_without_json=1), _snapshot())
    assert [m.key for m in broken] == ["ask_without_json"]
    assert moved == []


def test_a_regression_fails_even_when_something_else_improved():
    """Otherwise a real gain buys cover for a real loss."""
    before = _snapshot(ask_without_json=1, gate_false_positive_rate=12.0)
    moved, broken = _compare(before, _snapshot())
    assert [m.key for m in broken] == ["ask_without_json"]
    assert [m.key for m in moved] == ["gate_false_positive_rate"]


def test_breaking_a_guard_is_a_regression():
    moved, broken = _compare(_snapshot(), _snapshot(external_api_cost_usd=0.02))
    assert [m.key for m in broken] == ["external_api_cost_usd"]
    assert moved == []


@pytest.mark.parametrize("after, counts", [(10.1, False), (9.8, False), (9.6, True)])
def test_rate_drift_below_the_floor_is_not_movement(after, counts):
    """Adding clean documents lowers the rate without fixing anything."""
    moved, broken = _compare(_snapshot(), _snapshot(gate_false_positive_rate=after))
    assert [m.key for m in moved] == (["gate_false_positive_rate"] if counts else [])
    assert broken == []


def test_the_floor_is_symmetric():
    """One-sided, and every ordinary commit would fail the run instead."""
    moved, broken = _compare(_snapshot(), _snapshot(gate_false_positive_rate=10.6))
    assert moved == []
    assert broken == []


def test_a_number_that_becomes_measurable_counts():
    """Making the product measurable where it was not is the other way to finish.

    Without this, work that no existing number can see would be permanently
    unfinishable, and the rational move would be to stop attempting it.
    """
    before = _snapshot()
    before["ask_without_json"] = {"value": None}
    moved, broken = _compare(before, _snapshot(ask_without_json=1))
    assert broken == []
    assert [(m.key, m.is_new) for m in moved] == [("ask_without_json", True)]


def test_a_number_that_stops_being_measurable_does_not_count():
    """A probe that broke is not an achievement."""
    after = _snapshot()
    after["ask_without_json"] = {"value": None}
    moved, broken = _compare(_snapshot(), after)
    assert moved == []
    assert broken == []


def test_unclassified_numbers_default_to_context():
    """An unclassified number is one nobody has argued for yet."""
    assert pm.Metric("k", "k", 1).kind == pm.CONTEXT


def test_the_real_metric_set_classifies_everything_it_reports():
    collector = pm.collect()
    assert collector.metrics, "the probes reported nothing at all"
    assert {m.kind for m in collector.metrics} <= {pm.OUTCOME, pm.GUARD, pm.CONTEXT}
    assert any(m.kind == pm.OUTCOME for m in collector.metrics), (
        "no outcome number left: nothing could ever be reported as done"
    )


def test_a_snapshot_round_trips_through_compare():
    """`--save` then `--compare` against itself must report no movement."""
    collector = pm.collect()
    snapshot = pm._snapshot(collector)
    moved, broken = pm.compare(snapshot, snapshot, {m.key: m for m in collector.metrics})
    assert moved == []
    assert broken == []
