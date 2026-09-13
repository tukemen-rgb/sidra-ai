"""C-1774: analyze names "fetched but all withheld" apart from "no new commits".

``requires_inference`` needs ``indexed > 0``, so a changed repository whose new
commits/PRs/issues were fetched but entirely quarantined or blocked (indexed 0,
no error) fell to the "no new commits" wording - a false all-clear when new
external content arrived and was withheld. The reason now names the withholding
with counts and where to review, while a genuine no-new-commits keeps its exact
wording.
"""

from __future__ import annotations

import tempfile

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.pipeline import IngestionReport, RepositoryReport
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.evals.analyze_reason_names_withheld_content import (
    evaluate_analyze_reason_names_withheld_content,
)

_OLD_REASON = "no new commits since the last ingestion; model not invoked"


def _analyze(report):
    service = SidraService(Settings(data_dir=tempfile.mkdtemp()), model=EchoModelAdapter())
    service._pipeline = lambda: type("P", (), {  # type: ignore[method-assign]
        "ingest_all": lambda self, repositories=None, force=False: report
    })()
    return service.analyze_github()


def _report(*specs):
    return IngestionReport(repositories=[
        RepositoryReport(repository=r, changed=c, indexed=i, quarantined=q, blocked=b, error=e)
        for r, c, i, q, b, e in specs
    ])


def test_analyze_withheld_eval_passes():
    result = evaluate_analyze_reason_names_withheld_content()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_all_quarantined_is_not_reported_as_no_new_commits():
    out = _analyze(_report(("owner/one", True, 0, 2, 0, "")))
    reason = out["reason"]
    assert reason != _OLD_REASON
    assert "quarantin" in reason or "withheld" in reason
    assert "sidra-quarantine" in reason
    assert out["inference_skipped"] is True and out["analysis"] is None


def test_all_blocked_is_named_too():
    out = _analyze(_report(("owner/one", True, 0, 0, 3, "")))
    assert out["reason"] != _OLD_REASON
    assert "block" in out["reason"]


def test_genuine_no_new_commits_keeps_its_wording():
    out = _analyze(_report(("owner/one", False, 0, 0, 0, ""), ("owner/two", False, 0, 0, 0, "")))
    assert out["reason"] == _OLD_REASON
