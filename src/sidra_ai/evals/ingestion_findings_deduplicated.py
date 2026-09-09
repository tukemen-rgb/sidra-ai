"""Does the ingestion summary list each finding kind once, not once per doc?

C-1602. ``RepositoryReport.findings`` is extended with a label for every
document the gate flagged, so the same detector firing on several documents
listed its label several times: the summary showed 「secret:github_token」 three
times and read as three separate leaks. The counts carry how many; this list
carries which kinds, so ``to_dict`` now returns it order-preservingly
deduplicated, the way decks and documents dedup their sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionFindingsDedupResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ingestion_findings_deduplicated() -> IngestionFindingsDedupResult:
    from sidra_ai.ingestion.pipeline import RepositoryReport

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # Duplicates across documents collapse to distinct kinds, order preserved.
    rep = RepositoryReport(
        repository="r", changed=True, indexed=1, quarantined=3,
        findings=["secret:github_token", "pii:email", "secret:github_token",
                  "pii:email", "secret:github_token"],
    )
    out = rep.to_dict()["findings"]
    add(out == ["secret:github_token", "pii:email"], f"not deduped/ordered: {out}")
    add(len(out) == len(set(out)), "duplicates remain in the findings roll-up")
    add("secret:github_token" in out and "pii:email" in out,
        "a distinct finding kind was dropped by dedup")

    # No findings -> empty list; a single finding -> unchanged.
    add(RepositoryReport(repository="r", changed=False).to_dict()["findings"] == [],
        "empty findings did not stay empty")
    add(RepositoryReport(repository="r", changed=True,
                         findings=["oversized_input:byte_budget"]).to_dict()["findings"]
        == ["oversized_input:byte_budget"],
        "a single finding was altered")

    # First-seen order survives even when the first duplicate is not first.
    rep2 = RepositoryReport(repository="r", changed=True,
                            findings=["b", "a", "b", "c", "a"])
    add(rep2.to_dict()["findings"] == ["b", "a", "c"],
        f"first-seen order not preserved: {rep2.to_dict()['findings']}")

    # End to end: the same token in three document bodies is listed once.
    import sys
    if "tests" not in sys.path:
        sys.path.insert(0, "tests")
    import tempfile
    from pathlib import Path

    import conftest
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.ingestion.github_client import GitHubReadOnlyClient
    from sidra_ai.ingestion.state import StateStore
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="ingest-dedup-"))
    repo = "tukemen-rgb/site"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(GatePolicy(), allowed_repositories=(repo,),
                        quarantine_store=QuarantineStore(tmp / "q.jsonl"))
    store = DocumentStore(gate)
    fake = conftest.FakeGitHub()
    token = "ghp_" + "a" * 36
    fake.issue_body = "token is " + token
    fake.pr_body = "also " + token
    fake.commit_message = "rotate " + token
    client = GitHubReadOnlyClient(settings, transport=fake, sleep=lambda _: None)
    svc = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate,
                       client=client, state_store=StateStore(tmp / "state.json"))
    result = svc.analyze_github([repo])
    repo_findings = result["ingestion"]["repositories"][0]["findings"]
    add(repo_findings.count("secret:github_token") == 1,
        f"real ingest still repeats a label: {repo_findings}")
    add(len(repo_findings) == len(set(repo_findings)),
        f"real ingest findings contain duplicates: {repo_findings}")
    add(result["ingestion"]["repositories"][0]["quarantined"] >= 3,
        "the quarantine count regressed (dedup must not touch counts)")

    total = 9
    return IngestionFindingsDedupResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "IngestionFindingsDedupResult",
    "evaluate_ingestion_findings_deduplicated",
]
