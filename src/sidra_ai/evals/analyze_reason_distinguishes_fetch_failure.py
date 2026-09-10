"""Does /v1/github/analyze tell "nothing changed" apart from "couldn't fetch"?

C-1644. ``analyze_github`` skips the model whenever the ingestion report does
not require inference, and set one reason for it: "no new commits since the
last ingestion; model not invoked". But ``requires_inference`` is False both
when a repository genuinely has no new commits *and* when its fetch failed and
nothing could be checked at all. So an operator whose every fetch failed
(network, auth, or a TLS trust gap) read "no new commits" - all-clear - when
in truth not one repository was seen. The per-repository ``error`` sat in the
nested ingestion report, but the one line a human reads first was wrong.

The checks drive ``analyze_github`` with a stub pipeline for three reports -
all fetches failed, a genuine no-new-commits, and a mix of the two - and
assert the summary reason now names the failure (with a count and where to
find the errors) while the genuine case keeps its exact wording, and that the
per-repository error is still present in the response either way.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

_OLD_REASON = "no new commits since the last ingestion; model not invoked"


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    settings = Settings(data_dir=tempfile.mkdtemp())
    return SidraService(settings, model=EchoModelAdapter())


def _report(specs):
    """specs: list of (repo, changed, error, skipped_reason)."""
    from sidra_ai.ingestion.pipeline import IngestionReport, RepositoryReport

    repos = [
        RepositoryReport(
            repository=repo,
            changed=changed,
            indexed=0,
            error=error,
            skipped_reason=skipped,
        )
        for repo, changed, error, skipped in specs
    ]
    return IngestionReport(repositories=repos)


class _StubPipeline:
    def __init__(self, report):
        self._report = report

    def ingest_all(self, repositories=None, *, force=False):
        return self._report


def _analyze_with(report):
    service = _service()
    service._pipeline = lambda: _StubPipeline(report)  # type: ignore[method-assign]
    return service.analyze_github()


@dataclass(frozen=True)
class AnalyzeReasonResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_analyze_reason_distinguishes_fetch_failure() -> AnalyzeReasonResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    fetch_err = "GitHub request failed: [SSL: CERTIFICATE_VERIFY_FAILED]"

    # (a) every fetch failed
    all_failed = _analyze_with(_report([
        ("owner/one", False, fetch_err, "fetch_failed"),
        ("owner/two", False, fetch_err, "fetch_failed"),
    ]))
    add(all_failed["inference_skipped"] is True, "all-failed: inference not skipped")
    add(all_failed["analysis"] is None, "all-failed: analysis not None")
    add(all_failed["reason"] != _OLD_REASON,
        f"all-failed still reports 'no new commits': {all_failed['reason']!r}")
    add("2 of 2" in all_failed["reason"],
        f"all-failed reason omits the failed count: {all_failed['reason']!r}")
    add("ingestion.repositories" in all_failed["reason"],
        f"all-failed reason does not point to the errors: {all_failed['reason']!r}")
    add(all_failed["ingestion"]["repositories"][0]["error"] == fetch_err,
        "all-failed: per-repo error not preserved in response")

    # (b) genuine no new commits
    genuine = _analyze_with(_report([
        ("owner/one", False, "", "no_new_commits"),
        ("owner/two", False, "", "no_new_commits"),
    ]))
    add(genuine["inference_skipped"] is True, "genuine: inference not skipped")
    add(genuine["analysis"] is None, "genuine: analysis not None")
    add(genuine["reason"] == _OLD_REASON,
        f"genuine no-new-commits wording changed: {genuine['reason']!r}")

    # (c) mixed: one failed, one genuinely unchanged
    mixed = _analyze_with(_report([
        ("owner/one", False, fetch_err, "fetch_failed"),
        ("owner/two", False, "", "no_new_commits"),
    ]))
    add(mixed["reason"] != _OLD_REASON,
        f"mixed still reports 'no new commits': {mixed['reason']!r}")
    add("1 of 2" in mixed["reason"],
        f"mixed reason omits the failed count: {mixed['reason']!r}")
    add(mixed["inference_skipped"] is True, "mixed: inference not skipped")

    total = 12
    return AnalyzeReasonResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AnalyzeReasonResult",
    "evaluate_analyze_reason_distinguishes_fetch_failure",
]
