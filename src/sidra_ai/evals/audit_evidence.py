"""Offline regression for persisted Security finding evidence.

The security gate intentionally keeps audit metadata for rejected content, but
that metadata must never become a second path for secrets or PII to survive.
This suite exercises the real gate + quarantine persistence boundary so a
future redaction refactor cannot re-introduce raw neighboring context while
unit tests still pass in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.security.decisions import Decision, FindingCategory
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate


def _synthetic_secret(seed: str) -> str:
    """Build a credential-like assignment value without provider prefixes."""

    return (seed + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4")[:28]


def run_audit_evidence_suite() -> tuple[EvalOutcome, ...]:
    """Prove gate/quarantine audit evidence cannot retain adjacent secrets."""

    first = _synthetic_secret("q7R")
    second = _synthetic_secret("v9T")
    content = f"password={first} token={second}"
    failures: list[str] = []

    with TemporaryDirectory(prefix="sidra-eval-audit-") as tmp:
        quarantine = QuarantineStore(Path(tmp) / "quarantine.jsonl")
        gate = SecurityGate(GatePolicy(), quarantine_store=quarantine)
        result = gate.inspect(content, source="operator", repository="")
        entries = quarantine.entries()

    if result.decision is not Decision.QUARANTINE:
        failures.append(
            f"adjacent assigned secrets should quarantine, got {result.decision.value}"
        )

    persisted = json.dumps(
        {"gate": result.to_dict(), "quarantine": entries},
        ensure_ascii=False,
        sort_keys=True,
    )
    for value in (first, second):
        if value in persisted:
            failures.append("raw synthetic secret survived in persisted audit metadata")

    secret_findings = [
        finding
        for finding in result.findings
        if finding.category is FindingCategory.SECRET
    ]
    if len(secret_findings) < 2:
        failures.append(
            f"expected at least two secret findings, got {len(secret_findings)}"
        )
    for finding in secret_findings:
        if finding.evidence and not finding.evidence.startswith("<<redacted len="):
            failures.append(
                f"finding evidence retained context for detector {finding.detector}"
            )

    if not entries:
        failures.append("quarantine audit record was not persisted")

    return (
        EvalOutcome(
            case_name="security_audit_evidence_context_free",
            passed=not failures,
            detail="GateResult and quarantine records retain metadata without raw neighboring secrets",
            failures=tuple(failures),
        ),
    )
