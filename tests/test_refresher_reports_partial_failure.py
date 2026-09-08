"""C-1482: the refresher status shows a partial ingestion failure.

run_once recorded a tick as clean success unless the whole ingest raised, so a
repository that persistently fails to fetch (while others succeed) was hidden.
The status now carries repositories_failed - the number of repositories that
reported an error in the most recent completed refresh.
"""

from __future__ import annotations

from types import SimpleNamespace

from sidra_ai.api.refresher import BackgroundRefresher
from sidra_ai.evals.refresher_reports_partial_failure import (
    evaluate_refresher_reports_partial_failure,
)


def _report(*repos):
    return SimpleNamespace(repositories=list(repos))


def _repo(changed, error=""):
    return SimpleNamespace(changed=changed, error=error)


def test_refresher_partial_failure_eval_passes():
    result = evaluate_refresher_reports_partial_failure()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_partial_failure_is_visible_in_status():
    reports = iter([_report(_repo(True), _repo(False, "not found"))])
    ref = BackgroundRefresher(ingest=lambda: next(reports), interval_seconds=60)
    st = ref.run_once()
    assert st.repositories_failed == 1
    assert st.repositories_changed == 1
    assert st.last_error_type == ""  # the refresher itself ran
    assert st.to_dict()["repositories_failed"] == 1


def test_failure_count_clears_on_recovery():
    reports = iter([_report(_repo(False, "boom")), _report(_repo(True))])
    ref = BackgroundRefresher(ingest=lambda: next(reports), interval_seconds=60)
    ref.run_once()
    assert ref.status().repositories_failed == 1
    assert ref.run_once().repositories_failed == 0


def test_whole_ingest_exception_still_recorded():
    def boom():
        raise RuntimeError("down")

    ref = BackgroundRefresher(ingest=boom, interval_seconds=60)
    st = ref.run_once()
    assert st.last_error_type == "RuntimeError"
    assert st.consecutive_failures == 1
