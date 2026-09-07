"""Does the ingestion summary report blocked files, not only quarantined ones?

C-1460: ``IngestionReport.to_dict`` aggregated ``total_indexed`` and
``total_quarantined`` but not blocked files (Decision.BLOCK: an unpermitted
source or a block-severity finding), even though every ``RepositoryReport``
counts them. So the top-level ingestion summary an operator reads after
``/v1/github/analyze`` accounted for fewer files than were fetched, and the two
rejection classes - held for review vs refused outright - were surfaced
inconsistently. The aggregate now carries ``total_blocked`` beside
``total_quarantined``.

The checks build reports directly and read the aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass


def _report(*triples):
    from sidra_ai.ingestion.pipeline import IngestionReport, RepositoryReport

    return IngestionReport(repositories=[
        RepositoryReport(repository=name, changed=True, indexed=i,
                         quarantined=q, blocked=b)
        for name, i, q, b in triples
    ])


@dataclass(frozen=True)
class IngestionBlockedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ingestion_report_totals_blocked() -> IngestionBlockedResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    mixed = _report(("a", 5, 2, 3), ("b", 1, 0, 1))  # blocked sum = 4
    d = mixed.to_dict()

    add("total_blocked" in d, "to_dict is missing total_blocked")
    add(d.get("total_blocked") == 4,
        f"total_blocked aggregate wrong: {d.get('total_blocked')!r} (want 4)")
    add(getattr(mixed, "total_blocked", None) == 4,
        f"total_blocked property wrong: {getattr(mixed, 'total_blocked', None)!r}")
    # Surfaced consistently with the other rejection class.
    add("total_blocked" in d and "total_quarantined" in d,
        "total_blocked is not surfaced alongside total_quarantined")

    # A zero-blocked report still carries the key (0, not absent), so a reader
    # never has to guess whether zero means none or means unreported.
    zero = _report(("c", 3, 1, 0)).to_dict()
    add(zero.get("total_blocked") == 0,
        f"zero-blocked report should report 0, got {zero.get('total_blocked')!r}")

    # Matches the sum of the per-repository counts it aggregates.
    three = _report(("x", 0, 0, 2), ("y", 0, 0, 5), ("z", 0, 0, 1)).to_dict()
    add(three.get("total_blocked") == sum(r["blocked"] for r in three["repositories"]),
        "total_blocked does not equal the sum of per-repository blocked counts")

    total = 6
    return IngestionBlockedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["IngestionBlockedResult", "evaluate_ingestion_report_totals_blocked"]
