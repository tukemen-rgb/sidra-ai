"""Run the eval suite.

Usable from pytest and from the command line::

    python -m sidra_ai.evals.runner
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Sequence

from sidra_ai.evals.audit_path_safety import run_audit_path_safety_suite
from sidra_ai.evals.cases import GATE_CASES, EvalOutcome, GateCase
from sidra_ai.evals.claim_coverage import run_claim_citation_coverage_suite
from sidra_ai.evals.fetch_response_integrity import run_fetch_response_integrity_suite
from sidra_ai.evals.grounding import run_grounding_suite
from sidra_ai.evals.health_resilience import run_health_resilience_suite
from sidra_ai.evals.literal_support import run_literal_support_suite
from sidra_ai.evals.output_security import run_output_security_suite
from sidra_ai.evals.policy_polarity import run_policy_polarity_suite
from sidra_ai.evals.retrieval_quality import run_retrieval_quality_suite
from sidra_ai.evals.runtime_model_admission import run_runtime_model_admission_suite
from sidra_ai.evals.startup_safety import run_startup_safety_suite
from sidra_ai.security.gate import GatePolicy, SecurityGate


@dataclass
class EvalReport:
    outcomes: list[EvalOutcome] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.passed)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "total": len(self.outcomes),
            "passed": self.passed,
            "failed": self.failed,
            "failures": [
                {"case": o.case_name, "failures": list(o.failures)}
                for o in self.outcomes
                if not o.passed
            ],
        }


def _make_gate() -> SecurityGate:
    return SecurityGate(
        GatePolicy(max_input_bytes=512 * 1024),
        allowed_repositories=(
            "tukemen-rgb/site",
            "tukemen-rgb/creater-yard",
            "tukemen-rgb/Fg",
            "tukemen-rgb/marketing",
            "tukemen-rgb/sidra-ai",
        ),
    )


def run_gate_case(case: GateCase, gate: SecurityGate | None = None) -> EvalOutcome:
    gate = gate or _make_gate()
    result = gate.inspect(case.content, source=case.source, repository=case.repository)

    failures: list[str] = []
    if result.decision is not case.expected_decision:
        failures.append(
            f"expected decision {case.expected_decision.value}, "
            f"got {result.decision.value} ({'; '.join(result.reasons) or 'no reason'})"
        )

    for category in case.expected_categories:
        if not result.has(category):
            failures.append(f"expected a {category.value} finding, none reported")

    for forbidden in case.must_not_appear:
        if forbidden in result.content:
            failures.append(
                f"sensitive value survived into gate output ({len(forbidden)} chars)"
            )

    return EvalOutcome(
        case_name=case.name,
        passed=not failures,
        detail=result.decision.value,
        failures=tuple(failures),
    )


def run_all(cases: Sequence[GateCase] = GATE_CASES) -> EvalReport:
    """Run input/output security, grounding, retrieval, API resilience, and startup regressions."""

    gate = _make_gate()
    report = EvalReport()
    for case in cases:
        report.outcomes.append(run_gate_case(case, gate))
    report.outcomes.extend(run_output_security_suite())
    report.outcomes.extend(run_grounding_suite())
    report.outcomes.extend(run_claim_citation_coverage_suite())
    report.outcomes.extend(run_policy_polarity_suite())
    report.outcomes.extend(run_literal_support_suite())
    report.outcomes.extend(run_retrieval_quality_suite())
    report.outcomes.extend(run_health_resilience_suite())
    report.outcomes.extend(run_startup_safety_suite())
    report.outcomes.extend(run_runtime_model_admission_suite())
    report.outcomes.extend(run_audit_path_safety_suite())
    report.outcomes.extend(run_fetch_response_integrity_suite())
    return report


def main(argv: Sequence[str] | None = None) -> int:
    report = run_all()
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
