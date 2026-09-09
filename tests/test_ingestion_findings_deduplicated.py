"""C-1602: the ingestion summary lists each finding kind once, not per document.

``RepositoryReport.findings`` gets a label per flagged document, so a detector
firing on several documents repeated its label. ``to_dict`` now dedups it
order-preservingly; the counts still carry how many.
"""

from __future__ import annotations

from sidra_ai.evals.ingestion_findings_deduplicated import (
    evaluate_ingestion_findings_deduplicated,
)
from sidra_ai.ingestion.pipeline import RepositoryReport


def test_ingestion_findings_dedup_eval_passes():
    result = evaluate_ingestion_findings_deduplicated()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_duplicate_labels_collapse_preserving_order():
    rep = RepositoryReport(
        repository="r", changed=True,
        findings=["secret:github_token", "pii:email", "secret:github_token"],
    )
    assert rep.to_dict()["findings"] == ["secret:github_token", "pii:email"]


def test_counts_are_untouched_by_dedup():
    rep = RepositoryReport(
        repository="r", changed=True, indexed=2, quarantined=3, blocked=1,
        findings=["a", "a", "a"],
    )
    out = rep.to_dict()
    assert out["indexed"] == 2 and out["quarantined"] == 3 and out["blocked"] == 1
    assert out["findings"] == ["a"]
