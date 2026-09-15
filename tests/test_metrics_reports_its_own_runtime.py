"""C-1521: the judge script says where its time went.

The script takes 200-300 seconds and this machine is shared by three loops,
so a run that goes long has to be able to say where the time went rather
than leave the next loop to separate its own cost from the weather.

**Corrected 2026-09-15 (C-1859)**: this docstring used to open with
"``test_script_runs_and_prints_a_table`` gives ``product_metrics.py`` 300
seconds", and that was not true - the test passes ``timeout=900``, raised
by C-1613 with the note "a hang-guard, not a performance contract". The
same sentence sat in three places and was read as "seconds from a red
test" three times, once into an escalation. Measured rather than argued: a
deliberate ``sleep(60)`` took a run to 327s and that test passed. The 300
is an advisory line worth looking at, and the report now says so.

This loop spent most of a cycle on exactly that, and reached the wrong
answer twice before instrumenting: first blaming ``create_app`` (rewriting
the caller changed nothing), then reading a 198s-vs-306s comparison as
"my change added 108 seconds" when the section actually cost 7.1.

Nothing here makes the script faster. It makes the script report, so the
next loop reads the answer instead of rediscovering it.
"""

from __future__ import annotations

import contextlib
import re
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


def _only(collector, key):
    """The one metric with this key, or a failure that names what is there."""

    found = [m for m in collector.metrics if m.key == key]
    assert len(found) == 1, f"{key}: {[m.key for m in collector.metrics]}"
    return found[0]


def test_the_report_names_the_budget_it_is_measured_against() -> None:
    """A loop reading a timeout should not have to find the number in a
    traceback - and it should not be told the wrong one.

    This used to assert the report said "a run is allowed" next to the 300.
    Nothing allowed 300: the suite passes ``timeout=900``, raised there by
    C-1613 as "a hang-guard, not a performance contract". Measured before
    the wording changed - a deliberate ``sleep(60)`` took a run to 327s and
    ``test_script_runs_and_prints_a_table`` passed - so the old assertion
    was pinning a false sentence in place (C-1859).
    """

    report = pm._runtime_report(_collector(answers=40.0), 250.0)
    head = report.splitlines()[0]

    assert f"{pm.SUBPROCESS_BUDGET_SECONDS:.0f}s" in head
    assert "advisory" in head, "the 300 has to be named as what it is"
    assert "a run is allowed" not in report, (
        "nothing allows 300 seconds; that phrasing is what three loops read "
        "as 'this tree is seconds from a red test'"
    )
    enforced = pm.enforced_timeout_seconds()
    assert enforced is not None and f"{enforced:.0f}s" in head, (
        "the limit that actually fails has to be on the same line as the "
        "one that does not"
    )


def test_the_enforced_limit_is_read_from_the_test_that_holds_it() -> None:
    """Not restated here, because restating it is how it went wrong.

    The constant said 300 and the test said 900, side by side, with nothing
    to notice the gap. Reading it means a change to the test moves the
    report with it.
    """

    from pathlib import Path

    written = re.findall(
        r"timeout=(\d+)",
        (Path(pm.ROOT) / pm._ENFORCED_IN).read_text(encoding="utf-8"),
    )
    assert written, "the test names no timeout for the report to read"
    assert pm.enforced_timeout_seconds() == max(float(n) for n in written)


def test_a_killed_run_has_already_said_which_sections_finished() -> None:
    """The case the section times exist for, run as it actually happens.

    The report is assembled after the last section returns, so before this
    a run killed by the suite's timeout printed nothing at all about where
    the time had gone - the numbers existed and the one case needing them
    could not reach them.
    """

    from sidra_ai.evals.overrun_says_why import evaluate_overrun_says_why

    result = evaluate_overrun_says_why()

    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total


def test_the_report_ranks_the_sections_worst_first() -> None:
    report = pm._runtime_report(
        _collector(usable=1.0, answers=40.0, gate=9.0), 200.0
    )

    body = report[report.index("Slowest sections:") :]
    assert body.index("answers") < body.index("gate") < body.index("usable")


def test_the_report_says_how_much_room_is_left() -> None:
    """The distance is still signed and still labelled - to what, changed.

    It used to read "of headroom", against a line nothing enforced, and the
    warning beside it said a loaded machine could "push this run over".
    Nothing was over: measured, a 327s run passed (C-1859). The number and
    its sign are the part worth keeping, so they are still pinned here.
    """

    tight = pm._runtime_report(_collector(answers=40.0), 290.0)
    roomy = pm._runtime_report(_collector(answers=40.0), 100.0)

    assert "+10.0s to the advisory line" in tight
    assert "Past the advisory line, or nearly" in tight, (
        "a run near the line still has to say so - quietly, but it says so"
    )
    assert "+200.0s to the advisory line" in roomy
    assert "Past the advisory line" not in roomy
    for report in (tight, roomy):
        assert "Close to the budget" not in report, (
            "'budget' is the word that made three loops read an advisory "
            "line as a failing test"
        )


def test_a_run_past_the_advisory_line_reports_a_negative_distance() -> None:
    """The case a loop is actually staring at - and it is not a failure.

    A run at 330s is 30s past the advisory line and 570s short of the only
    limit that fails anything, and the report has to say both so the next
    loop does not escalate on the first.
    """

    report = pm._runtime_report(_collector(answers=40.0), 330.0)
    head = report.splitlines()[0]

    assert "-30.0s to the advisory line" in head
    assert "Nothing fails here" in head
    enforced = pm.enforced_timeout_seconds()
    assert enforced is not None and f"{enforced - 330.0:+.0f}s away" in head


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


# ----------------------------------------------------------- C-1736


@contextlib.contextmanager
def counting(stub=None):
    """Count spawns without making any.

    ``_spawn_timing`` wraps whatever ``subprocess.run`` is at the moment it
    is installed, so a stub put in first is what the wrapper calls. That
    keeps these tests off the clock and off node: what is under test is the
    bookkeeping, and a real spawn would only add a second of weather to it.
    """

    import subprocess

    real = subprocess.run
    subprocess.run = stub or (lambda *a, **k: None)
    kept_counts = dict(pm._SPAWN_THREADS)
    kept_sites = dict(pm._SPAWNS)
    pm._spawn_timing()
    pm._SPAWN_THREADS.update(bundled=0, alone=0)
    try:
        yield pm._SPAWN_THREADS
    finally:
        subprocess.run = real
        pm._SPAWN_THREADS.update(kept_counts)
        pm._SPAWNS.clear()
        pm._SPAWNS.update(kept_sites)


def _spawn_node():
    import subprocess

    subprocess.run(["node", "-"], input="", capture_output=True, text=True)


def test_a_spawn_on_the_main_thread_is_counted_as_waiting_alone() -> None:
    """The number exists to say how much of the run queues. A site that
    never left the main thread is the whole of what it is counting."""

    with counting() as counts:
        _spawn_node()

        assert counts == {"bundled": 0, "alone": 1}


def test_spawns_handed_to_workers_are_counted_as_bundled() -> None:
    with counting() as counts:
        pm.in_parallel([_spawn_node, _spawn_node, _spawn_node])

        assert counts == {"bundled": 3, "alone": 0}


def test_one_job_through_in_parallel_still_reads_as_alone() -> None:
    """``in_parallel`` runs a lone job on the caller's thread, and a lone
    job *is* alone - a count that called it bundled would report a site as
    fixed by wrapping it in a list."""

    with counting() as counts:
        pm.in_parallel([_spawn_node])

        assert counts == {"bundled": 0, "alone": 1}


def test_the_run_s_other_subprocesses_are_not_counted() -> None:
    """The claim is about node. git, python and the suites this script
    shells out to are spawns too, and counting them would let the number
    move without a single probe being bundled."""

    import subprocess

    with counting() as counts:
        subprocess.run(["git", "status"], capture_output=True)
        subprocess.run(["python3", "-c", "pass"], capture_output=True)

        assert counts == {"bundled": 0, "alone": 0}


@pytest.mark.parametrize(
    "cmd,is_node",
    [
        (["node", "-"], True),
        (["/usr/local/bin/node", "--check", "-"], True),
        (["nodemon", "x"], False),
        (["python3", "-c", "pass"], False),
        ("node", True),
    ],
)
def test_node_is_recognised_by_the_program_not_the_prefix(cmd, is_node: bool) -> None:
    assert pm._is_node((cmd,), {}) is is_node
    assert pm._is_node((), {"args": cmd}) is is_node


def test_the_share_is_reported_as_an_outcome_with_both_counts() -> None:
    kept = dict(pm._SPAWN_THREADS)
    pm._SPAWN_THREADS.update(bundled=3, alone=1)
    try:
        collector = pm.Collector()
        pm.measure_runtime(collector)
    finally:
        pm._SPAWN_THREADS.update(kept)

    # By key, not by position: measure_runtime reports more than one number
    # and the order is not a contract - asserting metrics[0] broke the day
    # another metric was added ahead of it (C-1859), which is a fact about
    # the test, not about the number.
    metric = _only(collector, "metrics_node_work_is_bundled")
    assert metric.value == 75.0
    assert metric.kind == pm.OUTCOME
    assert metric.direction == "up"
    assert "3" in metric.detail and "1" in metric.detail, (
        "the share alone cannot say whether a probe was added or bundled"
    )


def test_a_run_that_spawned_no_node_says_so_instead_of_reporting_zero() -> None:
    """0% would read as "nothing is bundled", which is a measurement. No
    spawn at all is not one."""

    kept = dict(pm._SPAWN_THREADS)
    pm._SPAWN_THREADS.update(bundled=0, alone=0)
    try:
        collector = pm.Collector()
        pm.measure_runtime(collector)
    finally:
        pm._SPAWN_THREADS.update(kept)

    metric = _only(collector, "metrics_node_work_is_bundled")
    assert metric.value is None
    assert metric.kind == pm.OUTCOME
    assert "no node spawn" in metric.detail


def test_the_runtime_section_runs_last() -> None:
    """It reports what every other section spent. Registered anywhere else
    it would report a part of the run and call it the run."""

    assert pm.COLLECTORS[-1][0] == "runtime"


@pytest.mark.parametrize(
    "worker",
    [
        # C-1736
        "_world_one", "_daily_one", "_fresh_one",
        # C-1746
        "_ghost_one", "_all_one", "_ts2_one", "_start_one", "_ink_one",
        # C-1751
        "_brief_one", "_open_one", "_afk_one", "_mash_one",
        "_rot_one", "_fs_one", "_gap_one", "_tick_one",
        # C-1755
        "_share_one", "_clk_one", "_pop_one", "_tie_one",
        "_touch_one", "_round_one", "_tune_one", "_streak_one",
        # C-1757
        "_carry_one", "_quiet_one", "_cost_one", "_hud_one",
    ],
)
def test_the_bundled_template_probes_stay_bundled(worker: str) -> None:
    """These eight were moved off the main thread by measurement (C-1736,
    then C-1746). A later loop editing one back into a ``for`` loop would
    put its spawns back in the queue - 557 between them, half of every
    node spawn the run makes - and the only sign would be a number
    nobody reads.

    Every one of them has the same shape: the runs *inside* one template
    are a chain, and the templates are independent. That is the shape to
    look for when bundling the next one; it is not a licence to wrap any
    loop in ``in_parallel``.
    """

    source = (ROOT / "scripts" / "product_metrics.py").read_text(encoding="utf-8")

    import re

    assert f"def {worker}(" in source, "the probe was renamed; check it is still bundled"
    # The loop variable differs from probe to probe, so the shape is what
    # is pinned: a default-argument lambda handed straight to in_parallel.
    driven = re.search(
        r"in_parallel\(\[\(lambda \w+=\w+: " + re.escape(worker) + r"\(", source
    )
    assert driven, f"{worker} is no longer driven through in_parallel"


def test_no_bundled_worker_appends_to_a_list_it_does_not_own() -> None:
    """The bug class C-1755 found, stated once so it cannot come back.

    A bundled probe returns its findings; it must not reach out and append
    to a list living in the section around it. Two reasons, and the second
    is the one that actually bit:

    1. Workers finish in whatever order the pool decides, so a shared list
       comes out shuffled, and these lists are joined into the detail a
       person reads.
    2. Far worse: several probes keep a second list for templates they do
       *not* measure - a clock that never runs long enough to be urgent is
       recorded as unmeasured, not as a pass. When the loop became a
       worker, "record it as unmeasured and move on" was translated into
       "return no gaps", and the caller read no gaps as a pass. Two
       metrics then described ten templates as driven when seven were.
       Neither value moved, so ``--compare`` said nothing; the details
       did, which is how it was caught.

    The rule that removes both: a worker owns every list it appends to.
    """

    import ast

    source = (ROOT / "scripts" / "product_metrics.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    escaped: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.endswith("_one"):
            continue
        owned = {a.arg for a in node.args.args}
        for inner in ast.walk(node):
            if isinstance(inner, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = inner.targets if isinstance(inner, ast.Assign) else [inner.target]
                for t in targets:
                    for name in ast.walk(t):
                        if isinstance(name, ast.Name):
                            owned.add(name.id)
            elif isinstance(inner, (ast.For, ast.comprehension)):
                target = inner.target
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        owned.add(name.id)
            elif isinstance(inner, ast.withitem) and inner.optional_vars is not None:
                for name in ast.walk(inner.optional_vars):
                    if isinstance(name, ast.Name):
                        owned.add(name.id)

        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "append"
                and isinstance(inner.func.value, ast.Name)
                and inner.func.value.id not in owned
            ):
                escaped.append(
                    f"{node.name} appends to {inner.func.value.id} "
                    f"(line {inner.lineno}), which it does not own"
                )

    assert not escaped, "; ".join(escaped)


# ----------------------------------------------------------- C-1760


def test_the_report_says_what_is_left_to_win_by_bundling() -> None:
    """The question that closed C-1760, answered by the run itself.

    Five cycles went into moving node spawns onto worker threads, and the
    yield per cycle fell the whole way (+7.5, +15.2, +7.5, +3.5 points).
    Deciding whether a sixth was worth it needed one number nobody was
    printing: what the still-serial sites actually cost, against the
    headroom the run already has. Measured once, it ended the question -
    so it is printed every run, and the next loop reads it instead of
    spending a cycle rediscovering it.
    """

    collector = _collector(creation=150.0)
    kept = dict(pm._SPAWNS)
    pm._SPAWNS.clear()
    pm._SPAWNS.update({
        # 40 spawns overlapping four ways: 80s of process in 21s of wall,
        # none of them on the main thread.
        "bundled.py:2": [40, 80.0, 0.0, 21.0, 0, 0.0],
        # 10 that waited alone on the main thread.
        "alone.py:1": [10, 20.0, 0.0, 20.0, 10, 20.0],
        # A site the span used to read backwards (C-1856): 200 spawns worth
        # 4s of process time, scattered over a 150s stretch of the run and
        # every one of them on a worker. wall >> sum, and nothing to win.
        "scattered.py:3": [200, 4.0, 10.0, 160.0, 0, 0.0],
    })
    try:
        report = pm._runtime_report(collector, 185.0)
    finally:
        pm._SPAWNS.clear()
        pm._SPAWNS.update(kept)

    # Read off the line itself, not the report. The budget line at the top
    # also carries the headroom, and asserting against the whole report let
    # a deliberate break - dropping the comparison from this line - pass.
    line = next(ln for ln in report.splitlines() if "waited alone" in ln)

    assert "10 of them, at 1 of 3 sites, waited alone" in line, (
        "the scattered site never queued behind anything - counting it "
        "sends the next loop to bundle work that is already beside another"
    )
    assert "cost 20.0s" in line, "the prize is the serial process time"
    assert "~15s" in line, "four-wide recovers about three quarters of it"
    assert "+115.0s of headroom" in line, (
        "the prize means nothing without the room already in hand - that "
        "comparison is the whole point of the line"
    )
