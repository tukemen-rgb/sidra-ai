"""Does /v1/github/analyze tell "nothing changed" apart from "all withheld"?

C-1774. ``analyze_github`` skips the model whenever the ingestion report does
not require inference. ``requires_inference`` needs ``indexed > 0`` (and no
error), so a repository whose new commits/PRs/issues were fetched but then
*entirely* quarantined or blocked by the gate - ``changed=True``, ``indexed=0``,
``error=""`` - leaves it False. C-1644 told a fetch failure apart from a genuine
no-new-commits, but this withheld case still fell to "no new commits since the
last ingestion" - a false all-clear precisely when new EXTERNAL content (an
Issue/PR body, the prompt-injection vector) arrived and was withheld, which is
the outcome an operator most needs to see.

``analyze_github`` now names the withholding, with counts and where to review,
while a genuine no-new-commits keeps its exact wording. The checks drive
``analyze_github`` with a stub pipeline, as the C-1644 eval does.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.evals.scratch import scratch_dir

_OLD_REASON = "no new commits since the last ingestion; model not invoked"


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    settings = Settings(data_dir=scratch_dir())
    return SidraService(settings, model=EchoModelAdapter())


def _report(specs):
    """specs: list of (repo, changed, indexed, quarantined, blocked, error)."""
    from sidra_ai.ingestion.pipeline import IngestionReport, RepositoryReport

    repos = [
        RepositoryReport(
            repository=repo,
            changed=changed,
            indexed=indexed,
            quarantined=quarantined,
            blocked=blocked,
            error=error,
        )
        for repo, changed, indexed, quarantined, blocked, error in specs
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
class AnalyzeWithheldResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_analyze_reason_names_withheld_content() -> AnalyzeWithheldResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # a changed repo whose every fetched document was quarantined
    quarantined = _analyze_with(_report([
        ("owner/one", True, 0, 2, 0, ""),
    ]))
    q_reason = quarantined.get("reason", "")

    # --- (A) it is not reported as "no new commits" ----------------------
    add(q_reason != _OLD_REASON,
        f"quarantined-all still reports 'no new commits': {q_reason!r}")

    # --- (B) the reason names that content was withheld/quarantined -------
    add("quarantin" in q_reason or "withheld" in q_reason,
        f"quarantined-all reason does not name the withholding: {q_reason!r}")

    # --- (C) the reason says where to review -----------------------------
    add("sidra-quarantine" in q_reason or "repositories[].quarantined" in q_reason,
        f"quarantined-all reason does not point to a review path: {q_reason!r}")

    # --- (D) the model was not spent -------------------------------------
    add(quarantined.get("inference_skipped") is True and quarantined.get("analysis") is None,
        "quarantined-all: model was invoked or analysis populated")

    # --- (E) a blocked-only repo is named too, not "no new commits" ------
    blocked = _analyze_with(_report([
        ("owner/one", True, 0, 0, 3, ""),
    ]))
    b_reason = blocked.get("reason", "")
    add(b_reason != _OLD_REASON and "block" in b_reason,
        f"blocked-all not named as withheld: {b_reason!r}")

    # --- (F) a genuine no-new-commits keeps its exact wording ------------
    #         (the withheld branch must not fire when nothing was withheld)
    genuine = _analyze_with(_report([
        ("owner/one", False, 0, 0, 0, ""),
        ("owner/two", False, 0, 0, 0, ""),
    ]))
    add(genuine.get("reason") == _OLD_REASON,
        f"genuine no-new-commits wording changed: {genuine.get('reason')!r}")

    total = 6
    return AnalyzeWithheldResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AnalyzeWithheldResult",
    "evaluate_analyze_reason_names_withheld_content",
]
