"""Does the first-run ingestion snapshot disclose when it hit the item cap?

C-1758. ``github_client.list_commits`` (first run), ``list_pull_requests`` and
``list_issues`` (non-incremental) cap the initial snapshot at
``max_items_per_source`` and return the newest N silently, while the *same file*
fails closed loudly for the analogous ``compare`` and ``list_docs_paths`` cases.
The setup step every user performs (``POST /v1/github/analyze``) therefore indexes
only the newest slice of a large repo with no ``error`` and no "capped" signal:
"never ingested" and "ingested only the newest N" look identical.

The fix keeps the intended bound (it does not fail closed) but names the bounded
sources: the pipeline records them on ``RepositoryReport.capped_sources``, which
``to_dict`` surfaces in the ``AnalyzeResponse.ingestion`` block, and
``analyze_github`` adds a human reason line. The checks drive the real pipeline
``_collect``/``_collect_activity`` with a client that returns more than the cap,
so the disclosure is read from running code.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass


LIMIT = 3  # a small cap so the fake only needs a handful of items


def _commit(i: int) -> dict:
    return {
        "sha": f"{i:040x}",
        "commit": {"message": f"c{i}", "author": {"name": "d", "date": "2026-08-01T00:00:00Z"}},
        "html_url": f"https://github.com/x/y/commit/{i}",
        "files": [{"filename": "README.md"}],
    }


def _pull(i: int) -> dict:
    return {
        "number": i, "title": f"pr{i}", "body": "b", "state": "open",
        "updated_at": "2026-08-01T00:00:00Z", "created_at": "2026-08-01T00:00:00Z",
        "merged_at": None, "head": {"sha": f"{i:040x}"},
        "user": {"login": "u", "type": "User"},
        "html_url": f"https://github.com/x/y/pull/{i}",
    }


def _issue(i: int) -> dict:
    return {
        "number": i, "title": f"is{i}", "body": "b", "state": "open",
        "updated_at": "2026-08-02T00:00:00Z", "created_at": "2026-08-02T00:00:00Z",
        "user": {"login": "u", "type": "User"},
        "html_url": f"https://github.com/x/y/issues/{i}",
    }


class _FakeClient:
    """Returns ``count`` of each source, bypassing pagination and the real cap.

    The detection lives in the pipeline (``len(...) >= limit``), so what matters
    is only how many rows each list method yields.
    """

    def __init__(self, count: int) -> None:
        self.count = count

    def list_commits(self, repository, since_sha=None, head=None):
        return [_commit(i) for i in range(self.count)]

    def list_pull_requests(self, repository, since=None):
        return [_pull(i) for i in range(self.count)]

    def list_issues(self, repository, since=None):
        return [_issue(i) for i in range(self.count)]

    def get_readme(self, repository, ref=None):
        return None

    def list_docs_paths(self, repository, ref=None):
        return []


def _pipeline(count: int):
    from sidra_ai.config.settings import Settings
    from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
    from sidra_ai.ingestion.state import StateStore
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    tmp = tempfile.mkdtemp()
    gate = SecurityGate(GatePolicy(), allowed_repositories=("x/y",))
    settings = Settings(data_dir=tmp, max_items_per_source=LIMIT)
    return GitHubIngestionPipeline(
        client=_FakeClient(count),
        store=DocumentStore(gate),
        state_store=StateStore(tmp + "/state.json"),
        gate=gate,
        settings=settings,
    )


def _collect_capped(count: int) -> list[str]:
    """Run the real first-run _collect; return capped_sources (or [] on baseline)."""

    pipe = _pipeline(count)
    result = pipe._collect(
        "x/y", head_sha="h" * 8, previous_sha="", license_id="MIT",
        first_run=True, since=None,
    )
    return list(result[5]) if len(result) > 5 else []


def _activity_capped(count: int, *, snapshot: bool) -> list[str]:
    pipe = _pipeline(count)
    try:
        res = pipe._collect_activity(
            "x/y", head_sha="h" * 8, license_id="MIT",
            since="2026-01-01T00:00:00Z", snapshot=snapshot,
        )
    except TypeError:  # baseline: no snapshot parameter yet
        res = pipe._collect_activity(
            "x/y", head_sha="h" * 8, license_id="MIT", since="2026-01-01T00:00:00Z",
        )
    return list(res[2]) if len(res) > 2 else []


@dataclass(frozen=True)
class SnapshotCapResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ingestion_snapshot_cap_is_disclosed() -> SnapshotCapResult:
    from sidra_ai.ingestion.pipeline import IngestionReport, RepositoryReport

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a first-run snapshot over the cap names "commits" -------------
    over = _collect_capped(LIMIT + 2)
    add("commits" in over, f"A: first-run commit cap not disclosed: {over}")

    # --- (B) ...and "pull_requests" and "issues" too ----------------------
    add("pull_requests" in over and "issues" in over,
        f"B: first-run PR/issue cap not disclosed: {over}")

    # --- (C) incremental activity polling must NOT flag a cap -------------
    #         (it drains the whole window; flagging would be a false positive)
    incremental = _activity_capped(LIMIT + 2, snapshot=False)
    add(incremental == [], f"C: incremental poll falsely flagged a cap: {incremental}")

    # --- (D) a first-run under the cap flags nothing ----------------------
    under = _collect_capped(LIMIT - 1)
    add(under == [], f"D: an under-cap snapshot falsely flagged: {under}")

    # --- (E) RepositoryReport.to_dict carries capped_sources -------------
    capped_report = RepositoryReport(repository="x/y", changed=True)
    try:
        capped_report.capped_sources = ["commits", "issues"]
    except Exception:
        pass
    wire = capped_report.to_dict()
    empty_wire = RepositoryReport(repository="z/w", changed=False).to_dict()
    add(wire.get("capped_sources") == ["commits", "issues"]
        and empty_wire.get("capped_sources") == [],
        f"E: to_dict does not carry capped_sources: {wire.get('capped_sources')!r}")

    # --- (F) analyze surfaces a human reason naming the capped repo -------
    try:
        from sidra_ai.ingestion.pipeline import snapshot_cap_reason
    except Exception:
        snapshot_cap_reason = None  # type: ignore[assignment]
    if snapshot_cap_reason is None:
        failures.append("F: no snapshot_cap_reason helper for analyze_github")
    else:
        r = RepositoryReport(repository="x/y", changed=True)
        r.capped_sources = ["commits"]
        report = IngestionReport(repositories=[r])
        reason = snapshot_cap_reason(report, LIMIT)
        empty_reason = snapshot_cap_reason(IngestionReport(repositories=[]), LIMIT)
        add("x/y" in reason and str(LIMIT) in reason and empty_reason == "",
            f"F: cap reason does not name the capped repo/bound: {reason!r}")

    total = 6
    return SnapshotCapResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["SnapshotCapResult", "evaluate_ingestion_snapshot_cap_is_disclosed"]
