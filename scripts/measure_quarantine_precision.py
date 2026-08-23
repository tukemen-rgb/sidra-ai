#!/usr/bin/env python3
"""Which documents the gate refuses to index, and whether it should have.

Why this exists
---------------

An ``analyze`` run over ``site`` printed a wall of ``high_entropy`` and
``email_role`` findings, and the obvious reading was that the gate is
quietly eating the corpus: every refused document is a document no question
can ever be answered from, so a noisy detector lowers the ceiling on the
answerable rate without appearing in any product number.

The obvious reading is not measurable from a findings list, because **a
finding is not a decision**. Role addresses are LOW and entropy hits are
MEDIUM; neither refuses a document on its own. This script reports the two
side by side so the alarm can be checked rather than believed:

* how many documents the gate actually refuses, per repository, and
* how many findings never changed a decision at all.

What it does not do
-------------------

It prints no document content: repository, path, decision and detector labels
only. The detected value is exactly what must not end up in a terminal, a log
or a CI artefact, and a false-positive report that leaks the true positives
is a worse bug than the one it is investigating.

It also does not judge. Whether a refusal was correct is a human reading of
each document; this script produces the list to read and the counts to record,
and ``docs/OUTCOMES.md`` carries the verdicts.

Usage
-----

    python scripts/measure_quarantine_precision.py \\
        tukemen-rgb/sidra-ai=. \\
        tukemen-rgb/site=/workspace/tukemen-rgb/site \\
        ...

Scope is the real ingestion scope - the README and documentation under
``docs/`` - via the same walk ``measure_outcomes.py`` uses. Measuring every
text file instead would count refusals of files SIDRA never reads, which is
how an earlier measurement described a system that does not exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "src"))

from measure_outcomes import iter_files, parse_targets  # noqa: E402
from sidra_ai.security.decisions import Decision  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402


def measure(targets: list[tuple[str, Path]]) -> dict:
    """Inspect every in-scope document and record decisions beside findings."""

    gate = SecurityGate(
        GatePolicy(), allowed_repositories=[name for name, _ in targets]
    )

    per_repo: dict[str, dict[str, int]] = {}
    refused: list[dict] = []
    findings_by_detector: dict[str, int] = {}
    findings_on_allowed = 0
    total = 0

    for repository, root in targets:
        counts = {"total": 0, "allow": 0, "quarantine": 0, "block": 0}
        for rel_path, content in iter_files(root):
            total += 1
            counts["total"] += 1
            result = gate.inspect(content, source="github", repository=repository)
            counts[result.decision.value] += 1
            for finding in result.findings:
                key = f"{finding.detector}:{finding.severity.value}"
                findings_by_detector[key] = findings_by_detector.get(key, 0) + 1
                if result.decision is Decision.ALLOW:
                    # The measurement the alarm actually needed: a finding
                    # that changed nothing about what SIDRA can answer.
                    findings_on_allowed += 1
            if result.decision is not Decision.ALLOW:
                refused.append({
                    "repository": repository,
                    "path": rel_path,
                    "decision": result.decision.value,
                    "detectors": sorted({
                        f"{f.detector}:{f.severity.value}" for f in result.findings
                    }),
                })
        per_repo[repository] = counts

    refused_total = sum(
        counts["quarantine"] + counts["block"] for counts in per_repo.values()
    )
    return {
        "documents": total,
        "refused": refused_total,
        "reachability_rate": ((total - refused_total) / total) if total else 0.0,
        "per_repository": per_repo,
        "refused_documents": refused,
        "findings_by_detector": dict(sorted(findings_by_detector.items())),
        "findings_on_indexed_documents": findings_on_allowed,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in arguments
    arguments = [a for a in arguments if a != "--json"]
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 2

    targets, missing = parse_targets(arguments)
    if not targets:
        print("no repository was checked out; nothing measured", file=sys.stderr)
        return 1

    report = measure(targets)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if missing:
        print(f"NOT MEASURED (not checked out): {', '.join(missing)}")
    print(f"{'repository':28s} {'docs':>6s} {'quar':>6s} {'block':>6s}")
    print("-" * 50)
    for repository, counts in report["per_repository"].items():
        print(f"{repository:28s} {counts['total']:6d} "
              f"{counts['quarantine']:6d} {counts['block']:6d}")
    print("-" * 50)
    print(f"{'合計':28s} {report['documents']:6d} {report['refused']:6d}")
    print(f"到達率 {100 * report['reachability_rate']:.1f}%"
          f"  ({report['documents'] - report['refused']}/{report['documents']})")

    print("\n--- 索引から外れた文書（値は出さない）---")
    for row in report["refused_documents"]:
        print(f"  {row['decision']:10s} {row['repository']:24s} {row['path']}")
        print(f"  {'':10s} {', '.join(row['detectors'])}")

    print("\n--- findings と決定の差 ---")
    print("finding が出ても決定が ALLOW なら索引に入っている。")
    print(f"索引に入った文書に出た findings: {report['findings_on_indexed_documents']} 件")
    for key, count in report["findings_by_detector"].items():
        print(f"  {key:28s} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
