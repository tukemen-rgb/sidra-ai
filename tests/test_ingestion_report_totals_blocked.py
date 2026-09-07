"""C-1460: the ingestion summary aggregates blocked files, not only quarantined.

blocked files (Decision.BLOCK) were counted per repository but never summed at
the top level, so the summary accounted for fewer files than were fetched.
"""

from __future__ import annotations

from sidra_ai.evals.ingestion_report_totals_blocked import (
    evaluate_ingestion_report_totals_blocked,
)
from sidra_ai.ingestion.pipeline import IngestionReport, RepositoryReport


def test_ingestion_blocked_eval_passes():
    result = evaluate_ingestion_report_totals_blocked()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_total_blocked_sums_per_repository():
    report = IngestionReport(repositories=[
        RepositoryReport(repository="a", changed=True, indexed=5, quarantined=2, blocked=3),
        RepositoryReport(repository="b", changed=True, indexed=1, quarantined=0, blocked=1),
    ])
    assert report.total_blocked == 4
    assert report.to_dict()["total_blocked"] == 4


def test_total_blocked_present_when_zero():
    report = IngestionReport(repositories=[
        RepositoryReport(repository="c", changed=True, indexed=3, quarantined=1, blocked=0),
    ])
    d = report.to_dict()
    assert d["total_blocked"] == 0
    assert "total_quarantined" in d and "total_blocked" in d
