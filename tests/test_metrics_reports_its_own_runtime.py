"""C-1521: the judge script says where its time went.

``test_script_runs_and_prints_a_table`` gives ``product_metrics.py`` 300
seconds and the script takes 200-300 of them, so on a loaded machine -
three loops share one here - the same tree is green or red depending on
what else is running. That would be tolerable if the failure said so. It
does not, so a loop that pushed a change and saw a timeout has no way to
separate its own cost from the weather.

This loop spent most of a cycle on exactly that, and reached the wrong
answer twice before instrumenting: first blaming ``create_app`` (rewriting
the caller changed nothing), then reading a 198s-vs-306s comparison as
"my change added 108 seconds" when the section actually cost 7.1.

Nothing here makes the script faster. It makes the script report, so the
next loop reads the answer instead of rediscovering it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import product_metrics as pm  # noqa: E402


def _collector(**timings: float) -> pm.Collector:
    collector = pm.Collector()
    collector.timings = list(timings.items())
    return collector


def test_the_report_names_the_budget_it_is_measured_against() -> None:
    """A loop reading a timeout should not have to find the 300 in a
    traceback."""

    report = pm._runtime_report(_collector(answers=40.0), 250.0)

    assert f"{pm.SUBPROCESS_BUDGET_SECONDS:.0f}s" in report
    assert "a run is allowed" in report


def test_the_report_ranks_the_sections_worst_first() -> None:
    report = pm._runtime_report(
        _collector(usable=1.0, answers=40.0, gate=9.0), 200.0
    )

    body = report[report.index("Slowest sections:") :]
    assert body.index("answers") < body.index("gate") < body.index("usable")


def test_the_report_says_how_much_room_is_left() -> None:
    tight = pm._runtime_report(_collector(answers=40.0), 290.0)
    roomy = pm._runtime_report(_collector(answers=40.0), 100.0)

    assert "+10.0s of headroom" in tight
    assert "Close to the budget" in tight, "a run one bad minute from red says nothing"
    assert "+200.0s of headroom" in roomy
    assert "Close to the budget" not in roomy


def test_a_run_over_the_budget_reports_negative_headroom() -> None:
    """The case a loop is actually staring at when the test failed."""

    report = pm._runtime_report(_collector(answers=40.0), 330.0)

    assert "-30.0s of headroom" in report


def test_every_section_is_timed_even_when_it_raises() -> None:
    """A probe that hangs and then fails is the one worth timing."""

    def boom(_c: pm.Collector) -> None:
        raise RuntimeError("probe fell over")

    def fine(c: pm.Collector) -> None:
        c.add("t", "t", 1.0)

    original = pm.COLLECTORS
    pm.COLLECTORS = (("boom", boom), ("fine", fine))
    try:
        collected = pm.collect()
    finally:
        pm.COLLECTORS = original

    assert [name for name, _ in collected.timings] == ["boom", "fine"]
    assert all(seconds >= 0 for _, seconds in collected.timings)
    assert any(m.key == "boom_probe" for m in collected.metrics), (
        "the broken probe stopped being reported"
    )


def test_the_sections_are_timed_in_the_order_they_ran() -> None:
    order = [name for name, _ in pm.COLLECTORS]

    def noop(_c: pm.Collector) -> None:
        return None

    original = pm.COLLECTORS
    pm.COLLECTORS = tuple((name, noop) for name in order)
    try:
        collected = pm.collect()
    finally:
        pm.COLLECTORS = original

    assert [name for name, _ in collected.timings] == order


@pytest.mark.parametrize("elapsed", [0.0, 0.5])
def test_a_run_shorter_than_its_sections_does_not_divide_by_zero(elapsed: float) -> None:
    """Guarded because the share is a percentage of the wall clock, and a
    stubbed or instant run has none."""

    report = pm._runtime_report(_collector(answers=0.1), elapsed)

    assert "Slowest sections:" in report


# ----------------------------------------------------------- C-1522


def test_parallel_results_come_back_in_the_order_asked_for() -> None:
    """The property that makes this safe to drop into a judge.

    Every caller is a loop that reasons about its results positionally -
    the third run of the second template - so a runner that returned them
    as they finished would silently re-pair every check with the wrong
    subject.
    """

    import random
    import time as _time

    def job(n: int):
        def run():
            _time.sleep(random.uniform(0, 0.05))
            return n
        return run

    assert pm.in_parallel([job(n) for n in range(12)]) == list(range(12))


def test_a_single_job_does_not_start_a_pool() -> None:
    """Most probes are one call. Paying for a thread pool to run one job
    would make the cheap sites slower to make the dear ones faster."""

    assert pm.in_parallel([lambda: "only"]) == ["only"]
    assert pm.in_parallel([]) == []


def test_a_failing_job_still_raises_to_its_caller() -> None:
    """A probe that falls over must not come back as a quiet None: the
    judges read ``(result, problem)`` pairs and a swallowed exception would
    read as 'no problem'."""

    def boom():
        raise RuntimeError("probe fell over")

    with pytest.raises(RuntimeError, match="probe fell over"):
        pm.in_parallel([lambda: 1, boom, lambda: 3])


def test_the_jobs_actually_overlap() -> None:
    """Otherwise this is a more complicated way to write a for loop."""

    import time as _time

    def sleeper():
        _time.sleep(0.4)
        return None

    started = _time.monotonic()
    pm.in_parallel([sleeper for _ in range(4)], workers=4)
    elapsed = _time.monotonic() - started

    assert elapsed < 1.0, f"four 0.4s jobs took {elapsed:.2f}s - they queued"
