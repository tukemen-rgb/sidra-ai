"""Does the background refresher's status show a partial ingestion failure?

C-1482. ``run_once`` records a tick as a clean success unless ``self.ingest()``
raises. But ``ingest_all`` never raises on a per-repo fetch failure - it returns
a report whose failing repository carries an ``error`` while the others succeed.
So a repository that persistently 404s (renamed, permissions revoked) was counted
only for what changed, its error dropped, and the status the operator polls said
``last_error_type=""`` with ``consecutive_failures`` reset - hiding that a repo
never updates. The module's own docstring promises "a failed refresh is
recorded"; a partial failure was not.

The status now carries ``repositories_failed`` - how many repositories reported
an error in the most recent completed refresh - so a persistent partial failure
is visible without conflating it with the refresher itself failing to run.

The checks drive ``BackgroundRefresher.run_once`` with reports it builds.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from sidra_ai.api.refresher import BackgroundRefresher


def _report(*repos):
    return SimpleNamespace(repositories=list(repos))


def _repo(changed, error=""):
    return SimpleNamespace(changed=changed, error=error)


@dataclass(frozen=True)
class RefresherPartialResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_refresher_reports_partial_failure() -> RefresherPartialResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # a tick where one repo failed and one succeeded
    reports = iter([_report(_repo(True), _repo(False, "not found: repos/x/y"))])
    ref = BackgroundRefresher(ingest=lambda: next(reports), interval_seconds=60)
    st = ref.run_once()
    add(getattr(st, "repositories_failed", None) == 1,
        f"partial failure not counted: {getattr(st, 'repositories_failed', None)}")
    add(st.repositories_changed == 1, f"changed repo miscounted: {st.repositories_changed}")
    # the refresher itself ran, so its own run signals stay honest (no exception)
    add(st.last_error_type == "", "a per-repo error was misreported as a refresher crash")
    add(st.last_success_at != "", "the tick that ran was not recorded as run")
    add(ref.status().to_dict().get("repositories_failed") == 1,
        "repositories_failed missing from the status dict")

    # an all-success tick reports zero, and clears a previous failure count
    reports2 = iter([
        _report(_repo(False, "boom")),
        _report(_repo(True), _repo(True)),
    ])
    ref2 = BackgroundRefresher(ingest=lambda: next(reports2), interval_seconds=60)
    ref2.run_once()
    add(getattr(ref2.status(), "repositories_failed", None) == 1, "first tick failure not recorded")
    st2 = ref2.run_once()
    add(getattr(st2, "repositories_failed", None) == 0,
        f"failure count not cleared on recovery: {getattr(st2, 'repositories_failed', None)}")
    add(st2.repositories_changed == 2, f"changed not accumulated: {st2.repositories_changed}")

    # a whole-ingest exception is still a refresher failure (existing behavior)
    def boom():
        raise RuntimeError("network down")

    ref3 = BackgroundRefresher(ingest=boom, interval_seconds=60)
    st3 = ref3.run_once()
    add(st3.last_error_type == "RuntimeError", "whole-ingest exception no longer recorded")
    add(st3.consecutive_failures == 1, "consecutive_failures not incremented on a crash")

    total = 10
    return RefresherPartialResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RefresherPartialResult", "evaluate_refresher_reports_partial_failure"]
